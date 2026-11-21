"""Rank every behaviour by measured similarity to leave-one-family-out knowledge."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .behaviours import Behaviour
from .cards import SourceCard, card_consumers
from .embedding import PipelineEmbeddingClient, embed_batches
from .generators import Notable, _behaviour_words, _make
from .knowledge import LoadedKnowledge, _unit_vector, load_for_run, statement_has_content

SIMILAR_GENERATOR = "similar_to_known"
SIMILAR_NOTABLE_BUDGET = 300  # effort budget: ranked candidates raised to an analyst
NEAREST_PER_LABEL = 3  # effort budget: nearest items shown from each label class
MATCH_BATCH_SIZE = 64  # effort budget: behavior vectors compared in one DuckDB query
CALIBRATION_QUERY_PER_GROUP = 128  # effort budget: calibration queries per family and class
CHANCE_AUC = 0.5  # the score-mode tie-break line; a measurement at chance must not switch it
_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_HOST_LABELS = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){2,}\.?$")


def _norm_token(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if "?" in text:
        text = text.split("?", 1)[0] + "?*"
    if _IPV4.match(text):
        return text
    if _HOST_LABELS.match(text) and any(char.isalpha() for char in text):
        parts = text.rstrip(".").split(".")
        return "*." + ".".join(parts[-2:])
    return re.sub(r"\d+", "#", text)[:48]


def _diversify_ranked(
    ranked: Sequence[tuple[float, int, Behaviour]],
) -> list[tuple[float, int, Behaviour]]:
    """Round-robin repeating numeric/host patterns so one template cannot monopolize the head."""
    counts: dict[tuple[str, str, str, str], int] = defaultdict(int)
    tagged: list[tuple[int, float, int, Behaviour]] = []
    for score, index, behaviour in ranked:
        pattern = (
            behaviour.source_id,
            _norm_token(behaviour.actor),
            _norm_token(behaviour.action),
            _norm_token(behaviour.object),
        )
        occ = counts[pattern]
        counts[pattern] += 1
        tagged.append((occ, score, index, behaviour))
    tagged.sort(
        key=lambda row: (
            row[0],
            -row[1],
            row[3].source_id,
            row[3].actor,
            row[3].action,
            row[3].object,
            row[2],
        )
    )
    return [(score, index, behaviour) for _occ, score, index, behaviour in tagged]


class SimilarityError(RuntimeError):
    """The similarity store cannot score behaviours under its recorded contract."""


def _auc(samples: Sequence[tuple[str, float]]) -> float:
    """Compute ROC AUC by average ranks, including ties."""
    positives = sum(1 for label, _score in samples if label == "known_bad")
    negatives = len(samples) - positives
    if not positives or not negatives:
        raise SimilarityError("similarity reliability needs known-bad and known-good examples")
    ordered = sorted(samples, key=lambda row: row[1])
    positive_ranks = 0.0
    offset = 0
    while offset < len(ordered):
        stop = offset + 1
        while stop < len(ordered) and ordered[stop][1] == ordered[offset][1]:
            stop += 1
        rank = (offset + 1 + stop) / 2
        positive_ranks += rank * sum(
            1 for label, _score in ordered[offset:stop] if label == "known_bad"
        )
        offset = stop
    return (positive_ranks - positives * (positives + 1) / 2) / (positives * negatives)


def _calibration_rows(pool: LoadedKnowledge) -> list[tuple[str, str, str, float, float]]:
    """Score a deterministic label-balanced sample against equal-size class pools per family."""
    connection = pool.connection
    counts = {
        (str(family), str(kind)): int(items)
        for family, kind, items in connection.execute(
            "SELECT family, label_kind, count(*) FROM loaded_knowledge GROUP BY 1,2"
        ).fetchall()
    }
    caps = {
        family: min(counts.get((family, "known_bad"), 0), counts.get((family, "known_good"), 0))
        for family in pool.families
    }
    cap_terms = [(family, cap) for family, cap in caps.items() if cap > 0]
    if not cap_terms:
        return []
    candidate_cap = " OR ".join(
        f"(family = ? AND row_no <= {int(cap)})" for _family, cap in cap_terms
    )
    connection.execute(
        "CREATE TEMP TABLE calibration_queries AS SELECT * FROM ("
        "SELECT *, row_number() OVER (PARTITION BY family, label_kind ORDER BY item_id) AS row_no "
        "FROM loaded_knowledge) WHERE row_no <= ?",
        [CALIBRATION_QUERY_PER_GROUP],
    )
    connection.execute(
        "CREATE TEMP TABLE calibration_candidates AS SELECT * FROM ("
        "SELECT *, row_number() OVER (PARTITION BY family, label_kind ORDER BY item_id) AS row_no "
        "FROM loaded_knowledge) WHERE " + candidate_cap,
        [family for family, _cap in cap_terms],
    )
    relation = "q.family <> c.family" if len(pool.families) > 1 else "q.item_id <> c.item_id"
    rows = connection.execute(
        "SELECT q.family, c.family, q.label_kind, "
        "max(array_inner_product(q.embedding,c.embedding)) FILTER "
        "(WHERE c.label_kind='known_bad') AS bad_score, "
        "max(array_inner_product(q.embedding,c.embedding)) FILTER "
        "(WHERE c.label_kind='known_good') AS good_score "
        "FROM calibration_queries q CROSS JOIN calibration_candidates c "
        f"WHERE {relation} GROUP BY q.item_id,q.family,c.family,q.label_kind ORDER BY q.item_id"
    ).fetchall()
    return [
        (str(query_family), str(candidate_family), str(label), float(bad), float(good))
        for query_family, candidate_family, label, bad, good in rows
        if bad is not None and good is not None
    ]


def _reliability(pool: LoadedKnowledge) -> dict[str, Any]:
    """Measure bad-only and bad-minus-good AUC inside each held-out fold, then average them."""
    rows = _calibration_rows(pool)
    folds: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for query_family, candidate_family, label, bad, good in rows:
        folds[f"{query_family}->{candidate_family}"].append((label, bad, good))
    measured = {
        name: {
            "known_bad_auc": _auc([(label, bad) for label, bad, _good in items]),
            "known_bad_minus_good_auc": _auc([(label, bad - good) for label, bad, good in items]),
            "queries": len(items),
        }
        for name, items in sorted(folds.items())
        if len({label for label, _bad, _good in items}) > 1
    }
    if not measured:
        raise SimilarityError("similarity reliability needs known-bad and known-good examples")
    bad_auc = sum(item["known_bad_auc"] for item in measured.values()) / len(measured)
    contrast_auc = sum(item["known_bad_minus_good_auc"] for item in measured.values()) / len(
        measured
    )
    # Keep the contrast score unless it ranks worse than chance while bad-only does not: on a
    # store where both are at chance the choice would otherwise flip from run to run.
    choice = "known_bad" if contrast_auc <= CHANCE_AUC < bad_auc else "known_bad_minus_good"
    return {
        "auc": bad_auc if choice == "known_bad" else contrast_auc,
        "score": choice,
        "known_bad_auc": bad_auc,
        "known_bad_minus_good_auc": contrast_auc,
        "method": "leave_one_family_out" if len(pool.families) > 1 else "leave_one_item_out",
        "validation_items": sum(item["queries"] for item in measured.values()),
        "folds": measured,
    }


def _insert_behaviours(
    pool: LoadedKnowledge,
    behaviours: Sequence[Behaviour],
    embedder: PipelineEmbeddingClient,
) -> None:
    """Stream normalized run vectors into DuckDB without retaining the full matrix in Python."""
    dimensions = pool.dimensions
    pool.connection.execute(
        "CREATE TEMP TABLE run_behaviours (behaviour_id BIGINT, statement VARCHAR, "
        f"embedding FLOAT[{dimensions}])"
    )
    by_statement: dict[str, list[int]] = defaultdict(list)
    for index, behaviour in enumerate(behaviours):
        by_statement[_behaviour_words(behaviour)].append(index)
    statements = list(by_statement)
    next_statement = 0
    for start, batch in embed_batches(embedder, statements):
        if start != next_statement or not batch:
            raise SimilarityError(
                f"Pipeline embedding batches are out of order at {next_statement}"
            )
        rows: list[tuple[int, str, list[float]]] = []
        for offset, vector in enumerate(batch):
            statement = statements[start + offset]
            normalized = _unit_vector(vector, dimensions)
            rows.extend((index, statement, normalized) for index in by_statement[statement])
        pool.connection.executemany(
            f"INSERT INTO run_behaviours VALUES (?,?, CAST(? AS FLOAT[{dimensions}]))",
            rows,
        )
        next_statement += len(batch)
    if next_statement != len(statements):
        raise SimilarityError(f"asked for {len(statements)} run embeddings, got {next_statement}")


def _scores(pool: LoadedKnowledge, count: int) -> dict[int, dict[str, float]]:
    """Score every run behaviour while retaining only two numeric best-match values per row."""
    scores: dict[int, dict[str, float]] = defaultdict(dict)
    for start in range(0, count, MATCH_BATCH_SIZE):
        rows = pool.connection.execute(
            "SELECT r.behaviour_id,k.label_kind,max(array_inner_product(r.embedding,k.embedding)) "
            "AS similarity FROM run_behaviours r CROSS JOIN loaded_knowledge k "
            "WHERE r.behaviour_id >= ? AND r.behaviour_id < ? "
            "GROUP BY r.behaviour_id,k.label_kind ORDER BY r.behaviour_id,k.label_kind",
            [start, min(start + MATCH_BATCH_SIZE, count)],
        ).fetchall()
        for behaviour_id, label_kind, similarity in rows:
            scores[int(behaviour_id)][str(label_kind)] = float(similarity)
    return scores


def _matches(
    pool: LoadedKnowledge, behaviour_ids: Sequence[int]
) -> dict[int, dict[str, list[dict[str, Any]]]]:
    """Find provenance for the top-ranked behaviors in bounded DuckDB batches."""
    connection = pool.connection
    found: dict[int, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"known_bad": [], "known_good": []}
    )
    for offset in range(0, len(behaviour_ids), MATCH_BATCH_SIZE):
        ids = list(behaviour_ids[offset : offset + MATCH_BATCH_SIZE])
        marks = ",".join("?" for _ in ids)
        rows = connection.execute(
            "WITH ranked AS (SELECT r.behaviour_id,k.item_id,k.label,k.label_kind,k.label_basis,k.family,"
            "k.index_name,k.source_kind,k.statement,k.provenance_query,"
            "array_inner_product(r.embedding,k.embedding) AS similarity,"
            "row_number() OVER (PARTITION BY r.behaviour_id,k.label_kind "
            "ORDER BY array_inner_product(r.embedding,k.embedding) DESC,k.item_id) AS rank "
            "FROM run_behaviours r CROSS JOIN loaded_knowledge k "
            f"WHERE r.behaviour_id IN ({marks})) "
            "SELECT behaviour_id,label,label_kind,label_basis,family,index_name,source_kind,statement,"
            "provenance_query,similarity FROM ranked WHERE rank <= ? "
            "ORDER BY behaviour_id,label_kind,rank",
            [*ids, NEAREST_PER_LABEL],
        ).fetchall()
        for (
            behaviour_id,
            label,
            kind,
            label_basis,
            family,
            index_name,
            source_kind,
            statement,
            query,
            similarity,
        ) in rows:
            found[int(behaviour_id)][str(kind)].append(
                {
                    "label": str(label),
                    "label_kind": str(kind),
                    "label_basis": str(label_basis),
                    "family": str(family),
                    "index": str(index_name),
                    "source_kind": str(source_kind),
                    "statement": str(statement),
                    "query": str(query),
                    "similarity": float(similarity),
                }
            )
    return found


def _ranked_notables(
    pool: LoadedKnowledge,
    behaviours: Sequence[Behaviour],
    cards: Sequence[SourceCard],
    scores: Mapping[int, Mapping[str, float]],
    reliability: Mapping[str, Any],
) -> list[Notable]:
    """Make the strongest measured known-bad similarities into normal notable records."""
    kinds_by_source: dict[str, set[str]] = defaultdict(set)
    eligible_sources: set[str] = set()
    for card in cards:
        kinds_by_source[card.source_id].add(card.kind)
        if "similar_to_known" in card_consumers(card):
            eligible_sources.add(card.source_id)
    invalid = sorted({item.source_id for item in behaviours} - eligible_sources)
    if invalid:
        invalid_details = [
            f"{source} (kinds: {', '.join(sorted(kinds_by_source[source])) or 'none'})"
            for source in invalid[:3]
        ]
        raise SimilarityError(
            "behaviour sources need an activity card with roles: " + "; ".join(invalid_details)
        )
    score_mode = str(reliability["score"])
    margins: dict[int, float] = {}
    ranked: list[tuple[float, int, Behaviour]] = []
    for index, behaviour in enumerate(behaviours):
        pair = scores.get(index, {})
        if "known_bad" not in pair or "known_good" not in pair:
            raise SimilarityError(f"missing known-bad or known-good match for behaviour {index}")
        bad_score = pair["known_bad"]
        margin = bad_score - pair["known_good"]
        margins[index] = margin
        score = margin if score_mode.endswith("minus_good") else bad_score
        ranked.append((score, index, behaviour))
    ranked.sort(
        key=lambda row: (
            -row[0],
            row[2].source_id,
            row[2].actor,
            row[2].action,
            row[2].object,
            row[1],
        )
    )
    top = _diversify_ranked(ranked)[:SIMILAR_NOTABLE_BUDGET]
    details = _matches(pool, [index for _score, index, _behaviour in top])
    notables = []
    for _score, index, behaviour in top:
        match_pair = details.get(index, {})
        bad: list[Mapping[str, Any]] = list(match_pair.get("known_bad") or ())
        good: list[Mapping[str, Any]] = list(match_pair.get("known_good") or ())
        if not bad or not good:
            raise SimilarityError(f"missing nearest reference for behavior {index}")
        nearest = sorted(
            [*bad, *good], key=lambda item: (-float(item["similarity"]), str(item["label"]))
        )
        notables.append(
            _make(
                generator=SIMILAR_GENERATOR,
                basis="nearest_known_behaviour",
                what=_behaviour_words(behaviour),
                entities=(
                    ("actor", behaviour.actor),
                    ("action", behaviour.action),
                    ("object", behaviour.object),
                ),
                source_id=behaviour.source_id,
                first_seen=behaviour.first_seen,
                last_seen=behaviour.last_seen,
                counts={
                    "events": behaviour.events,
                    "hosts": behaviour.hosts,
                    "actors": behaviour.actors,
                },
                measure_name="known_bad_minus_good",
                measure_value=margins[index],
                why=(
                    f"nearest known reference from {bad[0]['family']} "
                    f"at cosine {float(bad[0]['similarity']):.3f}; "
                    f"margin {margins[index]:.3f} (threshold 0); "
                    f"measured AUC {reliability['auc']:.3f}"
                ),
                evidence=(
                    {
                        "line": behaviour.example_raw,
                        "query": behaviour.example_query,
                        "earliest": behaviour.example_earliest,
                        "latest": behaviour.example_latest,
                    },
                ),
                nearest_known=nearest,
                generator_reliability=float(reliability["auc"]),
            )
        )
    return notables


def generate_similar(
    behaviours: Sequence[Behaviour],
    cards: Sequence[SourceCard],
    *,
    store_path: Path,
    run_index: str,
    expected_family: str | None,
    allowed_families: Sequence[str] | None,
    embedder: PipelineEmbeddingClient,
) -> tuple[list[Notable], dict[str, Any]]:
    """Score each behavior against the store after its family has been structurally removed."""
    began = time.monotonic()
    with load_for_run(
        store_path,
        run_index=run_index,
        expected_family=expected_family,
        allowed_families=allowed_families,
    ) as pool:
        if pool.embedding_model != embedder.model:
            raise SimilarityError(
                f"store model {pool.embedding_model!r} differs from Pipeline model {embedder.model!r}"
            )
        reliability = _reliability(pool)
        scored = [item for item in behaviours if statement_has_content(_behaviour_words(item))]
        statements = list(dict.fromkeys(_behaviour_words(item) for item in scored))
        if scored:
            _insert_behaviours(pool, scored, embedder)
            scores = _scores(pool, len(scored))
            notables = _ranked_notables(pool, scored, cards, scores, reliability)
        else:
            notables = []
        receipt = {
            "existed": len(behaviours),
            "scored": len(scored),
            "uninformative": len(behaviours) - len(scored),
            "kept": len(notables),
            "store": str(store_path),
            "run_index": pool.run_index,
            "excluded_family": pool.excluded_family,
            "excluded_families": list(pool.excluded_families),
            "index_unseen": pool.index_unseen,
            "loaded_families": list(pool.families),
            "knowledge_items": pool.items,
            "excluded_contradicted": pool.contradicted,
            "excluded_uninformative": pool.uninformative,
            "embedding_model": pool.embedding_model,
            "unique_statements": len(statements),
            "reliability": reliability,
            "embedding": embedder.stats(),
            "seconds": round(time.monotonic() - began, 3),
        }
    return notables, receipt
