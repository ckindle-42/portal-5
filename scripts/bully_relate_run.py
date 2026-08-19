#!/usr/bin/env python3
"""M.3 -- run investigations over real seeds harvested from connected
sources; record outcome distribution, relation confidence distribution,
ANOMALOUS rate, scored vs unscored split, coverage, cost, and the
compounding result (ordered halves, anchor write-back disabled as the
control arm). Publishes anchor-library composition and what the arriving
data could not be related to.

Requires the lab Splunk credentials sourced into the environment (the same
.env the L.6-L.10 live scripts use) and the staged corpora / attack_data
manifests under the local hunt volume.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from portal.modules.security.core.bully import compounding, degeneracy, measurement
from portal.modules.security.core.bully import relation as relation_mod
from portal.modules.security.core.bully import signatures as sig_mod
from portal.modules.security.core.bully.anchors import AnchorLibrary
from portal.modules.security.core.bully.coverage import coverage_records
from portal.modules.security.core.bully.live_census import build_live_plane
from portal.modules.security.core.bully.seed_scope import Seed, build_scope
from scripts.corpus_ingest import load_manifest_catalog

SEED_SOURCES = (
    "attack_data",
    "lab-splunk",
    "live-advisories",
    "flaws_cloud_cloudtrail",
    "invictus_ir_aws_dataset",
)


def _sample_actions_from_data_file(path: Path, *, limit: int = 32) -> list[str]:
    """Best-effort: attack_data's data.yml declares techniques but not
    action sequences, so pull a bounded sample of real events from the
    dataset file itself (NDJSON, one record per line) the same way seed
    records are read -- imperfect/absent formats degrade to an empty list,
    never an error (S1)."""
    if not path.is_file():
        return []
    actions: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for i, line in enumerate(handle):
                if i >= limit:
                    break
                record = _maybe_parse_json(line.strip())
                if not record:
                    continue
                flat = _unwrap_nested_record(record)
                for key in ("action", "eventName", "command", "cmdline", "verb"):
                    value = flat.get(key)
                    if isinstance(value, str):
                        actions.append(value)
                api = flat.get("api")
                if isinstance(api, dict) and isinstance(api.get("operation"), str):
                    actions.append(api["operation"])
    except OSError:
        return []
    return actions


def build_anchor_library(attack_data_root: Path, coverage_path: Path, plane: Any) -> AnchorLibrary:
    lib = AnchorLibrary()
    seen_datasets: set[str] = set()
    for manifest in load_manifest_catalog(attack_data_root):
        if not manifest.techniques:
            continue
        key = str(manifest.path.parent)
        if key in seen_datasets:
            continue
        seen_datasets.add(key)
        lib.load_attack_episode(
            source_id="attack_data",
            record={
                "action_sequence": _sample_actions_from_data_file(manifest.path),
                "telemetry_shape": {"source_class": manifest.mapped_sourcetype or ""},
                "context_topology": {"dataset": manifest.path.parent.name},
            },
            techniques=manifest.techniques,
        )
    if coverage_path.is_file():
        for rec in coverage_records(coverage_path):
            lib.load_detection_coverage(
                source_id="detection-coverage",
                detection_id=f"det-{rec['technique_id']}",
                techniques=(rec["technique_id"],),
                telemetry_shape={"sourcetypes": rec["sourcetypes"]},
            )
    for rec in plane.records.get("live-advisories", ()):
        if not isinstance(rec, dict):
            continue
        techniques = [
            t.get("technique_id") if isinstance(t, dict) else t
            for t in (rec.get("attack_mappings") or [])
        ]
        lib.load_advisory(
            source_id="live-advisories",
            technique=techniques[0] if techniques else None,
            ioc=rec.get("artifacts") or {},
            context=rec.get("context_topology") or {},
        )
    return lib


def _maybe_parse_json(value: Any) -> dict | None:
    if isinstance(value, str) and value.strip()[:1] == "{":
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _unwrap_nested_record(record: dict, *, depth: int = 3) -> dict:
    """Universal sources arrive imperfect (S1): lab-splunk wraps a raw
    event in `raw` -> `result` -> `_raw`, each itself a JSON string, rather
    than one flat schema. Best-effort unwrap; a source this doesn't
    recognize just yields the original record back, never an error."""
    merged = dict(record)
    current: Any = record
    for _ in range(depth):
        nested = None
        for key in ("raw", "_raw", "result"):
            candidate = current.get(key) if isinstance(current, dict) else None
            if isinstance(candidate, dict):
                nested = candidate
            elif isinstance(candidate, str):
                nested = _maybe_parse_json(candidate)
            if nested is not None:
                break
        if nested is None:
            break
        merged.update(nested)
        current = nested
    return merged


def _signature_from_scope(scope: Any) -> Any:
    actions: list[str] = []
    sourcetypes: set[str] = set()
    for record in scope.records:
        if not isinstance(record, dict):
            continue
        flat = _unwrap_nested_record(record)
        for key in ("action", "eventName", "command", "cmdline", "verb"):
            value = flat.get(key)
            if isinstance(value, str):
                actions.append(value)
        api = flat.get("api")
        if isinstance(api, dict) and isinstance(api.get("operation"), str):
            actions.append(api["operation"])
        st = flat.get("sourcetype") or flat.get("source") or flat.get("host")
        if st:
            sourcetypes.add(str(st))
    return sig_mod.build_signature(
        {"target_host": scope.source_id, "episode_id": scope.scope_id},
        {
            "action_sequence": actions[:32],
            "telemetry_shape": {"sourcetypes": sorted(sourcetypes)} if sourcetypes else {},
        },
    )


def harvest_seeds(plane: Any, *, per_source: int) -> list[tuple[Seed, str]]:
    seeds: list[tuple[Seed, str]] = []
    for source_id in SEED_SOURCES:
        if source_id not in plane.connectors:
            continue
        records = list(plane.records.get(source_id) or ())[:per_source]
        for i, _record in enumerate(records):
            kind = "detection_fire" if i % 2 == 0 else "operator_hunch"
            seeds.append((Seed(seed_id=f"seed-{source_id}-{i:03d}", kind=kind), source_id))
    return seeds


def run_pass(
    seeds: list[tuple[Seed, str]], plane: Any, anchor_library: AnchorLibrary, *, write_back: bool
) -> list[dict]:
    rows: list[dict] = []
    for seed, source_id in seeds:
        profile = plane.catalog.get(source_id)
        capabilities = profile.capabilities.as_dict() if profile else None
        scope = build_scope(seed, plane, source_id, scale_cap=32)
        signature = _signature_from_scope(scope)
        rel = relation_mod.relate(signature, anchor_library, capabilities=capabilities)
        rows.append(
            {
                "seed_id": seed.seed_id,
                "source_id": source_id,
                "verdict": rel.verdict,
                "confidence": rel.confidence,
                "uncertainty_reasons": list(rel.uncertainty_reasons),
                "scored": measurement.score_eligible(rel, anchor_library),
                "record_count": len(scope.records),
                "scope_degraded": scope.degraded,
            }
        )
        if write_back:
            outcome = (
                "ESCALATE"
                if rel.verdict in ("SAME", "SIMILAR", "NEW")
                else "ANOMALOUS_UNCLASSIFIED"
            )
            compounding.write_outcome_as_anchor(
                anchor_library,
                signature,
                source_id=f"observed:{source_id}",
                outcome=outcome,
                analyst_confirmed=False,
            )
    return rows


def _distribution(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "median": None, "min": None, "max": None}
    return {
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
    }


def _summarize(rows: list[dict]) -> dict[str, Any]:
    from collections import Counter

    outcomes = Counter(r["verdict"] for r in rows)
    scored = [r for r in rows if r["scored"]]
    unscored = [r for r in rows if not r["scored"]]
    fake_relations = [_relation_stub(r) for r in rows]
    anomaly_finding = degeneracy.check_anomaly_rate(fake_relations)
    variance_report = degeneracy.check_uncertainty_variance(fake_relations)
    return {
        "n": len(rows),
        "outcome_distribution": dict(outcomes),
        "confidence_distribution": _distribution([r["confidence"] for r in rows]),
        "anomalous_rate": anomaly_finding.rate,
        "anomalous_rate_ceiling": anomaly_finding.ceiling,
        "anomalous_rate_exceeded": anomaly_finding.exceeded,
        "scored_count": len(scored),
        "unscored_count": len(unscored),
        "coverage": len(scored) / len(rows) if rows else 0.0,
        "uncertainty_variance_passes": variance_report.passes,
        "uncertainty_distinct_reason_sets": variance_report.distinct_reason_sets,
        "data_access_records": sum(r["record_count"] for r in rows),
        "cost_tokens": 0,  # relation-only run: no model calls (J.1 brief-shaping is pure compute)
    }


def _relation_stub(row: dict) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        verdict=row["verdict"], uncertainty_reasons=tuple(row["uncertainty_reasons"])
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-source", type=int, default=20)
    parser.add_argument(
        "--output", type=Path, default=Path("docs/BULLY_RELATE_INVESTIGATE_RUN_M3_V1.json")
    )
    args = parser.parse_args()

    base = Path("/Volumes/data01/portal5_hunt")
    attack_data_root = base / "sources/attack_data/datasets"
    coverage_path = Path("portal/modules/security/core/siem/spl_detections.yaml")

    plane, planner_proof = build_live_plane(
        corpora_root=base / "corpora",
        attack_data_root=attack_data_root,
        coverage_path=coverage_path,
        store_path=base / "hunt_state.db",
        sample_limit=64,
        corpus_counts={
            "attack_data": 54,
            "flaws_cloud_cloudtrail": 1_939_207,
            "invictus_ir_aws_dataset": 2_900,
        },
    )

    seeds = harvest_seeds(plane, per_source=args.per_source)
    half = len(seeds) // 2

    control_library = build_anchor_library(attack_data_root, coverage_path, plane)
    control_composition = control_library.composition()
    control_rows = run_pass(seeds, plane, control_library, write_back=False)

    experiment_library = build_anchor_library(attack_data_root, coverage_path, plane)
    experiment_rows_first_half = run_pass(seeds[:half], plane, experiment_library, write_back=True)
    experiment_rows_second_half = run_pass(seeds[half:], plane, experiment_library, write_back=True)
    experiment_library_composition_after = experiment_library.composition()

    control_second_half = list(control_rows[half:])

    unrelatable = [
        row
        for row in control_rows
        if row["verdict"] == "ANOMALOUS_UNCLASSIFIED" and row["scored"] is False
    ]

    payload = {
        "schema": "BULLY_RELATE_INVESTIGATE_RUN_M3_V1",
        "planner_proof_hash": planner_proof.get("proof_hash"),
        "seed_count": len(seeds),
        "seed_sources": sorted({source_id for _seed, source_id in seeds}),
        "anchor_library_starting_composition": control_composition,
        "control_arm": {
            "description": "full ordered seed sequence, anchor write-back disabled throughout",
            **_summarize(control_rows),
        },
        "compounding_experiment": {
            "description": (
                "same ordered seed sequence split at the midpoint; write-back enabled "
                "after every seed, so the second half's anchor library has grown from "
                "the first half's outcomes -- compare its second-half summary against "
                "the control arm's second-half summary (write-back disabled) below"
            ),
            "first_half": _summarize(experiment_rows_first_half),
            "second_half_with_growth": _summarize(experiment_rows_second_half),
            "control_second_half_no_growth": _summarize(control_second_half),
            "anchor_library_composition_after": experiment_library_composition_after,
        },
        "unrelatable_coverage_gap": {
            "count": len(unrelatable),
            "fraction_of_seeds": len(unrelatable) / len(control_rows) if control_rows else 0.0,
            "sample": unrelatable[:10],
        },
        "rows": control_rows,
    }

    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))
    print(
        json.dumps(
            {
                "output": str(args.output),
                "seed_count": len(seeds),
                "control_outcome_distribution": payload["control_arm"]["outcome_distribution"],
                "control_coverage": payload["control_arm"]["coverage"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
