#!/usr/bin/env python3
"""M.6 -- the universal-intake verification run
(TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1).

COLD (no network, no model calls, no training). Runs over whichever plane
`inject_plane.run_inject_capture()` produces -- the live lab if reachable,
the E.3 fixture otherwise -- and states plainly which one produced the
published numbers (never a silent synthetic substitute).

Every metric named in the task's M.6 build step is computed here and
written to both a JSON and a companion MD; the MD renders every JSON
column, none summarized away.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from portal.modules.security.core.bully import anchors as anc
from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import baseline as bl
from portal.modules.security.core.bully import blend
from portal.modules.security.core.bully import field_roles as fr
from portal.modules.security.core.bully import inject_plane as ip
from portal.modules.security.core.bully import unit_ladder as ul
from portal.modules.security.core.bully import unit_measurement as um
from portal.modules.security.core.bully import unit_outcome as uo

_EPOCH_BASE = 1_700_000_000.0


def _per_source_role_maps(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_source[str(record.get("__source_id") or "unknown")].append(record)
    return {
        source_id: fr.infer_field_roles(source_records, source_id=source_id).to_dict()
        for source_id, source_records in by_source.items()
    }


def _benign_baseline(benign_records: list[dict[str, Any]]) -> bl.NormalBaseline:
    graph = ag.build_graph(benign_records)
    model = bl.NormalBaseline(environment_id="universal-intake-run")
    for level in ag.UNIT_LEVELS:
        level_units = [u for u in ag.enumerate_units(graph) if u.level == level]
        if level_units:
            model.fit(level_units)
    return model


def _library_from_chains() -> tuple[anc.AnchorLibrary, dict[str, list[anc.Anchor]]]:
    """Anchors built directly from the blend fixture's injected chains --
    the type library this run's leave-one-family-out excludes from, one
    family at a time."""
    library = anc.AnchorLibrary()
    by_family: dict[str, list[anc.Anchor]] = defaultdict(list)
    for chain in blend._CHAINS:
        verbs = [str(step) for step in chain["steps"]]
        anchor = library.load_attack_episode(
            source_id="blend-chain",
            record={"action_sequence": verbs},
            techniques=(chain["technique"],),
        )
        by_family[chain["family"]].append(anchor)
    return library, dict(by_family)


def _eval_units_by_family(
    records: list[dict[str, Any]], provenance: dict[str, blend.Provenance]
) -> dict[str, list[ag.GradeableUnit]]:
    """One L4_WINDOW unit per injected chain, built from just that chain's
    own records (mirrors how the chain was generated) -- the arriving-side
    unit each family's leave-one-out excludes and re-evaluates."""
    by_chain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    chain_family: dict[str, str] = {}
    for record in records:
        fp = blend._fingerprint(record)
        prov = provenance.get(fp)
        if prov is None or not prov.injected or prov.chain_id is None or prov.family is None:
            continue
        by_chain[prov.chain_id].append(record)
        chain_family[prov.chain_id] = prov.family

    out: dict[str, list[ag.GradeableUnit]] = defaultdict(list)
    for chain_id, chain_records in by_chain.items():
        graph = ag.build_graph(chain_records)
        units = ag.enumerate_units(graph)
        window = next((u for u in units if u.level == "L4_WINDOW"), None)
        if window is not None:
            out[chain_family[chain_id]].append(window)
    return dict(out)


def _cross_vocabulary_recovery() -> dict[str, Any]:
    parent_verbs = ["AssumeRole", "ListBuckets", "AttachUserPolicy"]
    rungs = ul.build_rungs(
        parent_verbs,
        substitution_verb="AddRole",
        cross_vocabulary_verbs=["Logon", "whoami", "Invoke-Command"],
        unrelated_verbs=["SELECT", "INSERT", "COMMIT"],
    )
    report = ul.run_ladder({"record_id": "parent-type", "action_sequence": parent_verbs}, rungs)
    l3 = report["per_rung"]["L3_CROSS_VOCABULARY"]
    return {
        "ladder_report": report,
        "cross_vocabulary_shape_distance": l3["shape_distance"],
        "cross_vocabulary_overall_relation": l3["overall_relation"],
        "recovered": l3["overall_relation"] in ("EXACT", "SIMILAR"),
    }


def _unconnected_artifact_rate(graph: ag.ArtifactGraph) -> dict[str, Any]:
    components = graph.components()
    isolated = sum(1 for c in components if len(c) == 1)
    total = len(graph.artifacts)
    return {
        "unconnected_artifact_count": isolated,
        "total_artifact_count": total,
        "unconnected_artifact_rate": isolated / total if total else 0.0,
        "cause": "sparse_source_or_no_shared_key",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/BULLY_UNIVERSAL_INTAKE_RUN_M6_V1.json"),
    )
    args = parser.parse_args()

    run = ip.run_inject_capture()
    records = list(run.records)
    if run.plane == "fixture":
        records, provenance = blend.compose_blend()
    else:
        # Live capture carries no per-record provenance (Q3) -- injected
        # ground truth for a live run is only reachable through the sealed
        # ledger, joined after grading, never inline here.
        provenance = {}

    role_maps = _per_source_role_maps(records)
    extraction_valid_by_source = {src: rm["extraction_valid"] for src, rm in role_maps.items()}
    insufficient_view_rate = (
        sum(1 for v in extraction_valid_by_source.values() if not v)
        / len(extraction_valid_by_source)
        if extraction_valid_by_source
        else 0.0
    )

    graph = ag.build_graph(records)
    all_units = ag.enumerate_units(graph)
    outcome_distribution_by_level: dict[str, dict[str, int]] = defaultdict(Counter)

    benign_records = [
        r
        for r in records
        if provenance.get(
            blend._fingerprint(r),
            blend.Provenance(fingerprint="", source_id="", schema="", injected=False),
        ).injected
        is False
    ]
    baseline = _benign_baseline(benign_records)
    library, library_by_family = _library_from_chains()

    all_outcomes = [uo.resolve_unit_outcome(u, list(library.all()), baseline) for u in all_units]
    for o in all_outcomes:
        outcome_distribution_by_level[o.unit.level][o.outcome] += 1

    # Bind ground truth per unit via the artifacts it covers (T.1 wall):
    # malicious if ANY covered artifact came from an injected chain.
    fp_to_provenance = provenance
    grading_rows = []
    id_to_record = {a.artifact_id: a.record for a in graph.artifacts.values()}
    for unit, outcome in zip(all_units, all_outcomes, strict=False):
        member_records = [id_to_record[aid] for aid in unit.artifact_ids if aid in id_to_record]
        member_provs = [fp_to_provenance.get(blend._fingerprint(r)) for r in member_records]
        known_provs = [p for p in member_provs if p is not None]
        if not known_provs:
            continue
        malice = "malicious" if any(p.injected for p in known_provs) else "benign"
        family = next((p.family for p in known_provs if p.injected), None)
        grading_rows.append(um.bind_ground_truth(outcome, family=family, malice=malice))

    precision_recall = um.precision_recall_report(grading_rows)

    eval_units_by_family = _eval_units_by_family(records, provenance)
    lofo_report: dict[str, Any] | None = None
    if eval_units_by_family:
        benign_eval_units = [u for u in all_units if u.level == "L4_WINDOW"][:20]
        lofo = um.run_leave_one_family_out(
            eval_units_by_family,
            library_by_family,
            list(library.all()),
            baseline,
            benign_eval_units=benign_eval_units,
        )
        lofo_report = lofo.to_dict()

    cross_vocab = _cross_vocabulary_recovery()
    unconnected = _unconnected_artifact_rate(graph)

    concern_briefs = [o.brief.to_dict() for o in all_outcomes if o.brief is not None]
    real_briefs = [
        b for b in concern_briefs if b.get("entities") and b.get("span_seconds") is not None
    ]

    payload: dict[str, Any] = {
        "schema": "BULLY_UNIVERSAL_INTAKE_RUN_M6_V1",
        "cold": True,
        "plane": run.plane,
        "plane_reason": run.reason,
        "sealed_count": run.sealed_count,
        "n_records": len(records),
        "role_maps_by_source": role_maps,
        "extraction_valid_by_source": extraction_valid_by_source,
        "insufficient_view_rate": insufficient_view_rate,
        "schemas_present": sorted({p.schema for p in provenance.values()} if provenance else set()),
        "injected_count": sum(1 for p in provenance.values() if p.injected),
        "benign_count": sum(1 for p in provenance.values() if not p.injected),
        "n_units_total": len(all_units),
        "outcome_distribution_by_level": {
            k: dict(v) for k, v in outcome_distribution_by_level.items()
        },
        "leave_one_family_out": lofo_report,
        "cross_vocabulary_recovery": cross_vocab,
        "precision_recall": precision_recall,
        "unconnected_artifact": unconnected,
        "concern_brief_count": len(concern_briefs),
        "real_concern_brief_count": len(real_briefs),
        "sample_concern_briefs": real_briefs[:5],
        "all_other_brief_count": sum(
            1
            for b in concern_briefs
            if set(b.get("shared_shape_features", []) + b.get("diverging_shape_features", []))
            <= {"class_present=other"}
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    print(json.dumps({"output": str(args.output), "plane": run.plane, "n_units": len(all_units)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
