#!/usr/bin/env python3
"""Measure provenance and behavior feature contributions in stored review pairs."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from portal.modules.security.core.bully import unit_relation

_ENTITY_ID = re.compile(r"entity=ent-\d{10}\Z", re.ASCII)


def _tokens(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, dict):
        return {f"{key}={token}" for key, inner in value.items() for token in _tokens(inner)}
    if isinstance(value, (list, tuple, set)):
        return {token for item in value for token in _tokens(item)}
    text = str(value).strip()
    return {text} if text else set()


def _distance(left: set[str], right: set[str]) -> float | None:
    if not left or not right:
        return None
    union = left | right
    return 1.0 - len(left & right) / len(union) if union else 0.0


def _record_provenance(*records: dict[str, Any], supplied: set[str]) -> set[str]:
    tokens = set(supplied)
    for record in records:
        tokens |= _tokens(record.get("provenance_tokens"))
        for field_name in ("source", "sourcetype"):
            values = _tokens(record.get(field_name))
            tokens |= values
            tokens.update(f"{field_name}={value}" for value in values)
    return tokens


def _pair_metrics(
    unit: dict[str, Any], anchor: dict[str, Any], *, supplied_provenance: set[str]
) -> dict[str, Any]:
    event_graph = unit.get("event_graph") or {}
    anchor_graph = anchor.get("event_graph") or {}
    unit_shape = unit_relation._class_sequence_tokens(
        tuple(event_graph.get("class_sequence") or ())
    )
    anchor_shape = unit_relation._type_shape_tokens(anchor, None)
    unit_actions = _tokens(unit.get("action_sequence"))
    anchor_actions = _tokens(anchor.get("action_sequence"))
    unit_parameters = _tokens(unit.get("parameter_families"))
    anchor_parameters = _tokens(anchor.get("parameter_families"))
    unit_vocabulary = unit_actions | unit_parameters
    anchor_vocabulary = anchor_actions | anchor_parameters
    union = unit_vocabulary | anchor_vocabulary
    shared = unit_vocabulary & anchor_vocabulary
    diverging = unit_vocabulary ^ anchor_vocabulary
    provenance = _record_provenance(unit, anchor, supplied=supplied_provenance)
    entity_ids = {token for token in union if _ENTITY_ID.fullmatch(token)}
    behavioral = (unit_actions | anchor_actions) - provenance - entity_ids
    provenance_union = union & provenance
    behavioral_union = union & behavioral
    entity_union = union & entity_ids
    other_union = union - provenance_union - behavioral_union - entity_union
    without_provenance = _distance(unit_vocabulary - provenance, anchor_vocabulary - provenance)
    without_nonbehavioral = _distance(
        unit_vocabulary - provenance - entity_ids,
        anchor_vocabulary - provenance - entity_ids,
    )
    return {
        "shape_distance": _distance(unit_shape, anchor_shape),
        "shape_unobservable": not unit_shape or not anchor_shape,
        "shape_union": unit_shape | anchor_shape,
        "shape_diverging": unit_shape ^ anchor_shape,
        "vocabulary_distance": _distance(unit_vocabulary, anchor_vocabulary),
        "vocabulary_union": union,
        "vocabulary_shared": shared,
        "vocabulary_diverging": diverging,
        "provenance_union": provenance_union,
        "behavioral_union": behavioral_union,
        "entity_id_union": entity_union,
        "other_union": other_union,
        "provenance_diverging": diverging & provenance,
        "behavioral_diverging": diverging & behavioral,
        "entity_id_diverging": diverging & entity_ids,
        "other_diverging": diverging & other_union,
        "distance_without_provenance": without_provenance,
        "distance_without_provenance_and_entity_ids": without_nonbehavioral,
    }


def _distance_stats(values: list[float | None]) -> dict[str, Any]:
    observed = [value for value in values if value is not None]
    return {
        "computed_pairs": len(observed),
        "unobservable_pairs": len(values) - len(observed),
        "mean": sum(observed) / len(observed) if observed else None,
        "min": min(observed) if observed else None,
        "max": max(observed) if observed else None,
    }


def _selected_pairs(
    connection: sqlite3.Connection,
    run_id: str,
    anchors: dict[str, dict[str, Any]],
    *,
    minimum: float,
    maximum: float,
    provenance_tokens: set[str],
) -> tuple[int, list[tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]]]]:
    rows = list(
        connection.execute(
            "SELECT payload_json, record_json FROM concerns WHERE run_id = ? ORDER BY concern_id",
            (run_id,),
        )
    )
    selected: list[tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        resembles = payload.get("resembles") or []
        if not resembles:
            continue
        pair = resembles[0]
        similarity = float(pair["similarity"])
        if not minimum <= similarity <= maximum:
            continue
        unit = json.loads(row["record_json"])
        anchor_id = str(pair.get("anchor_id") or "")
        anchor = anchors.get(anchor_id)
        if anchor is None:
            raise ValueError(f"concern references missing anchor {anchor_id!r}")
        metrics = _pair_metrics(unit, anchor, supplied_provenance=provenance_tokens)
        selected.append((similarity, unit, anchor, metrics))
    return len(rows), selected


def _token_census(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    category_union = Counter()
    category_diverging = Counter()
    feature_category = {"entity_ids": "entity_id"}
    for item in metrics:
        for category in ("provenance", "behavioral", "entity_ids", "other"):
            feature = feature_category.get(category, category)
            category_union[category] += len(item[f"{feature}_union"])
            category_diverging[category] += len(item[f"{feature}_diverging"])
    total_union = sum(category_union.values())
    total_diverging = sum(category_diverging.values())
    shape_features = Counter(token for item in metrics for token in item["shape_diverging"])
    return {
        "union_tokens": total_union,
        "diverging_tokens": total_diverging,
        "union_by_category": dict(category_union),
        "diverging_by_category": dict(category_diverging),
        "divergence_share_by_category": {
            name: count / total_diverging if total_diverging else None
            for name, count in category_diverging.items()
        },
        "shape_diverging_features": dict(shape_features.most_common(20)),
    }


def _pair_metadata(
    selected: list[tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]]],
    provenance_tokens: set[str],
) -> dict[str, Any]:
    source_occurrences = 0
    auth_action_pairs = 0
    auth_class_pairs = 0
    duplicate_auth_pairs = 0
    entity_ids: set[str] = set()
    entity_occurrences = 0
    entity_anchor_overlaps = 0
    anchor_source_fields = 0
    anchor_sourcetype_fields = 0
    for _similarity, unit, anchor, _metrics in selected:
        for token in _tokens(unit.get("action_sequence")):
            if token in provenance_tokens:
                source_occurrences += 1
        unit_entities = {
            token
            for token in _tokens(unit.get("parameter_families"))
            if _ENTITY_ID.fullmatch(token)
        }
        anchor_entities = {
            token
            for token in _tokens(anchor.get("parameter_families"))
            if _ENTITY_ID.fullmatch(token)
        }
        entity_ids.update(unit_entities | anchor_entities)
        entity_occurrences += len(unit_entities) + len(anchor_entities)
        if unit_entities & anchor_entities:
            entity_anchor_overlaps += 1
        anchor_source_fields += int("source" in anchor)
        anchor_sourcetype_fields += int("sourcetype" in anchor)
        anchor_actions = _tokens(anchor.get("action_sequence"))
        anchor_classes = set((anchor.get("event_graph") or {}).get("class_sequence") or ())
        has_auth_action = "auth" in anchor_actions
        has_auth_class = "auth" in anchor_classes
        auth_action_pairs += int(has_auth_action)
        auth_class_pairs += int(has_auth_class)
        duplicate_auth_pairs += int(has_auth_action and has_auth_class)
    return {
        "unit_occurrences_of_supplied_provenance_tokens": source_occurrences,
        "anchor_fields_on_selected_primary_pairs": {
            "with_source": anchor_source_fields,
            "with_sourcetype": anchor_sourcetype_fields,
        },
        "anchor_auth_action_sequence_pairs": auth_action_pairs,
        "anchor_auth_class_sequence_pairs": auth_class_pairs,
        "anchor_auth_duplicated_across_action_and_class_sequence": duplicate_auth_pairs,
        "window_entity_id_occurrences": entity_occurrences,
        "unique_window_entity_ids": len(entity_ids),
        "pairs_sharing_window_entity_id_with_anchor": entity_anchor_overlaps,
    }


def _summarize_run(
    connection: sqlite3.Connection,
    run_id: str,
    anchors: dict[str, dict[str, Any]],
    *,
    minimum: float,
    maximum: float,
    provenance_tokens: set[str],
) -> dict[str, Any]:
    concerns_seen, selected = _selected_pairs(
        connection,
        run_id,
        anchors,
        minimum=minimum,
        maximum=maximum,
        provenance_tokens=provenance_tokens,
    )
    metrics = [pair[3] for pair in selected]
    similarities = [pair[0] for pair in selected]
    tokens = _token_census(metrics)
    metadata = _pair_metadata(selected, provenance_tokens)
    return {
        "run_id": run_id,
        "concerns_seen": concerns_seen,
        "primary_pairs_in_similarity_band": len(metrics),
        "similarity_band": [minimum, maximum],
        "observed_similarity": {
            "min": min(similarities) if similarities else None,
            "max": max(similarities) if similarities else None,
        },
        "shape_distance": _distance_stats([item["shape_distance"] for item in metrics]),
        "shape_diverging_features": tokens["shape_diverging_features"],
        "vocabulary_distance": _distance_stats([item["vocabulary_distance"] for item in metrics]),
        "vocabulary_distance_without_provenance": _distance_stats(
            [item["distance_without_provenance"] for item in metrics]
        ),
        "vocabulary_distance_without_provenance_or_entity_ids": _distance_stats(
            [item["distance_without_provenance_and_entity_ids"] for item in metrics]
        ),
        "vocabulary_union_tokens": tokens["union_tokens"],
        "vocabulary_diverging_tokens": tokens["diverging_tokens"],
        "vocabulary_union_by_category": tokens["union_by_category"],
        "vocabulary_diverging_by_category": tokens["diverging_by_category"],
        "vocabulary_divergence_share_by_category": tokens["divergence_share_by_category"],
        **metadata,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--run-id", action="append", required=True)
    parser.add_argument("--provenance-token", action="append", required=True)
    parser.add_argument("--minimum-similarity", type=float, default=0.87)
    parser.add_argument("--maximum-similarity", type=float, default=0.91)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output = args.output.expanduser().resolve()
    repository = Path(__file__).resolve().parents[1]
    if output.is_relative_to(repository):
        raise ValueError("measurement output must be outside the checkout")
    if args.minimum_similarity > args.maximum_similarity:
        raise ValueError("minimum similarity exceeds maximum similarity")
    database_uri = f"{args.database.expanduser().resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    anchors = {
        str(row["anchor_id"]): json.loads(row["record_json"])
        for row in connection.execute("SELECT anchor_id, record_json FROM anchors")
    }
    report = {
        "schema": "SOURCE_TOKEN_ASYMMETRY_MEASUREMENT_V1",
        "database_mode": "read_only",
        "provenance_tokens": sorted(set(args.provenance_token)),
        "anchor_population": len(anchors),
        "anchors_with_source_field": sum("source" in record for record in anchors.values()),
        "anchors_with_sourcetype_field": sum("sourcetype" in record for record in anchors.values()),
        "runs": [
            _summarize_run(
                connection,
                run_id,
                anchors,
                minimum=args.minimum_similarity,
                maximum=args.maximum_similarity,
                provenance_tokens=set(args.provenance_token),
            )
            for run_id in args.run_id
        ],
    }
    connection.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
