"""labelled_corpus answer key: leak filter, entity ranking, and truth derivation.

The BOTS derivation rejects any dataset outside ``BOTS_INDEXES``. This module is the mirror for
``labelled_corpus`` and forces ``match_all`` so an entry's entities must co-occur.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from portal.modules.security.core.bully.corpus_bed import LABELLED_CORPUS_INDEX, AnswerKeyEntry
from portal.modules.security.core.bully.telemetry_behavior import classify_record
from portal.modules.security.core.review_eval.truth import (
    DayCountFetcher,
    RecordFetcher,
    StatsFetcher,
    TruthDerivation,
    derive_bots_truth,
)

KEY_PATH = Path(__file__).with_name("corpus_truth_key.json")
SELECTION_RULE = (
    "dominant UTC day of one single-technique attack_data item; "
    "host plus artifact by cooccurrence/((1+host_corpus)*(1+artifact_corpus)); "
    "full TERM() only; drop events whose _raw names a technique id or "
    "Atomic/Stratus Red Team; drop an entity on every sensor day; match_all; "
    "unique entity sets"
)
_TECHNIQUE_ID = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.IGNORECASE)
_RED_TEAM = re.compile(
    r"atomic[\s_-]*red[\s_-]*team|stratus[\s_-]*red[\s_-]*team",
    re.IGNORECASE,
)
LEAK_MATCH = (
    r'match(_raw, "\bT\d{4}(\.\d{3})?\b") OR '
    r'match(_raw, "(?i)atomic[\s_-]*red[\s_-]*team") OR '
    r'match(_raw, "(?i)stratus[\s_-]*red[\s_-]*team")'
)
LEAK_WHERE = f"where NOT ({LEAK_MATCH})"


def raw_leaks_label(raw: str) -> bool:
    """True when ``_raw`` names a technique id or Atomic/Stratus Red Team."""
    return bool(raw and (_TECHNIQUE_ID.search(raw) or _RED_TEAM.search(raw)))


@dataclass(frozen=True)
class EntityCandidate:
    host: str
    artifact: str
    cooccurrence: int
    host_corpus: int
    artifact_corpus: int
    host_days: int
    artifact_days: int
    host_term_indexed: bool = True
    artifact_term_indexed: bool = True


def pair_score(candidate: EntityCandidate) -> float:
    """Rarity-weighted co-occurrence. Higher is a rarer pair that still co-occurs."""
    return candidate.cooccurrence / ((1 + candidate.host_corpus) * (1 + candidate.artifact_corpus))


def _background(entity_days: int, sensor_days: int) -> bool:
    return sensor_days > 1 and entity_days >= sensor_days


def _entity_set(candidate: EntityCandidate) -> frozenset[str]:
    return frozenset({candidate.host.casefold(), candidate.artifact.casefold()})


def _eligible(
    candidate: EntityCandidate,
    sensor_days: int,
    used_sets: frozenset[frozenset[str]],
) -> bool:
    if candidate.cooccurrence < 1:
        return False
    if not (candidate.host_term_indexed and candidate.artifact_term_indexed):
        return False
    if len(candidate.host) < 3 or len(candidate.artifact) < 3:
        return False
    if candidate.host.casefold() == candidate.artifact.casefold():
        return False
    if raw_leaks_label(candidate.host) or raw_leaks_label(candidate.artifact):
        return False
    if _background(candidate.host_days, sensor_days) or _background(
        candidate.artifact_days, sensor_days
    ):
        return False
    entity_set = _entity_set(candidate)
    return len(entity_set) == 2 and entity_set not in used_sets


def _rank_key(candidate: EntityCandidate) -> tuple[float, int, int, int, str, str]:
    return (
        pair_score(candidate),
        -candidate.artifact_corpus,
        -candidate.host_corpus,
        candidate.cooccurrence,
        candidate.artifact.casefold(),
        candidate.host.casefold(),
    )


def rank_entity_pairs(
    candidates: Sequence[EntityCandidate],
    sensor_days: int,
    used_sets: frozenset[frozenset[str]] | set[frozenset[str]] = frozenset(),
) -> tuple[EntityCandidate, ...]:
    """Best host+artifact first. Background, leaks, and used sets are omitted."""
    used = frozenset(used_sets)
    eligible = [candidate for candidate in candidates if _eligible(candidate, sensor_days, used)]
    return tuple(sorted(eligible, key=_rank_key, reverse=True))


def select_pairs(
    grouped: Mapping[str, Sequence[EntityCandidate]],
    sensor_days: Mapping[str, int],
    order: Sequence[str],
) -> dict[str, EntityCandidate]:
    """One pair per technique, refusing an entity set already given to another."""
    used: set[frozenset[str]] = set()
    chosen: dict[str, EntityCandidate] = {}
    for technique in order:
        ranked = rank_entity_pairs(grouped.get(technique, ()), sensor_days.get(technique, 0), used)
        if not ranked:
            continue
        pair = ranked[0]
        used.add(_entity_set(pair))
        chosen[technique] = pair
    return chosen


def _observation_sourcetype(indexed: str, record: Mapping[str, Any]) -> str:
    raw = record.get("_raw")
    text = raw.casefold() if isinstance(raw, str) else ""
    if "microsoft-windows-sysmon" in text:
        return "xmlwineventlog:sysmon"
    if "<channel>security</channel>" in text:
        return "wineventlog:security"
    return indexed


def behaviour_spine(records: Sequence[Mapping[str, Any]], sourcetype: str) -> tuple[str, ...]:
    """Modal ``classify_record`` class for a clean sample, or empty when none classify."""
    counts: dict[str, int] = {}
    for record in records:
        label = classify_record(dict(record), _observation_sourcetype(sourcetype, record))
        if label:
            counts[label] = counts.get(label, 0) + 1
    if not counts:
        return ()
    winner = min(counts, key=lambda name: (-counts[name], name))
    return (winner,)


def derive_labelled_corpus_truth(
    fetch_records: RecordFetcher,
    query_stats: StatsFetcher,
    *,
    entries: Sequence[AnswerKeyEntry],
    query_days: DayCountFetcher | None = None,
) -> TruthDerivation:
    """Derive ``labelled_corpus`` truth. Every declared entity must share each kept event."""
    for entry in entries:
        if entry.dataset != LABELLED_CORPUS_INDEX:
            raise ValueError(f"answer-key dataset {entry.dataset!r} is not {LABELLED_CORPUS_INDEX}")
    return derive_bots_truth(
        fetch_records,
        query_stats,
        entries=entries,
        query_days=query_days,
        match_all=True,
        allowed_indexes=(LABELLED_CORPUS_INDEX,),
    )


def _spine(row: Mapping[str, Any]) -> tuple[str, ...]:
    raw = row.get("behavioural_spine", ())
    if not raw:
        return ()
    return tuple(str(item) for item in raw)


def _entry_from_row(row: Mapping[str, Any]) -> AnswerKeyEntry:
    confirmed = row.get("confirmed_at")
    entry = AnswerKeyEntry(
        dataset=str(row["dataset"]),
        technique=str(row["technique"]),
        behavioural_spine=_spine(row),
        entities=tuple(str(item) for item in row["entities"]),
        sourcetypes=tuple(str(item) for item in row["sourcetypes"]),
        confirmed_at=None if confirmed is None else float(confirmed),
    )
    if entry.dataset != LABELLED_CORPUS_INDEX or len(entry.entities) < 2 or not entry.sourcetypes:
        raise ValueError(f"corpus entry {entry.technique} is incomplete")
    return entry


def load(path: Path = KEY_PATH) -> tuple[AnswerKeyEntry, ...]:
    """Load the generated key. Provenance is required; raw telemetry is not in the file."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} must be a JSON object")
    provenance = document.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("index") != LABELLED_CORPUS_INDEX:
        raise ValueError(f"{path} provenance must name {LABELLED_CORPUS_INDEX}")
    if not provenance.get("rule"):
        raise ValueError(f"{path} provenance must record the selection rule")
    rows = document.get("entries")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path} must list entries")
    return tuple(_entry_from_row(row) for row in rows)
