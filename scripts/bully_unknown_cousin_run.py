#!/usr/bin/env python3
"""M.3 -- the unknown-cousin verification run (TASK_BULLY_UNKNOWN_COUSIN_V1).

Real local data, COLD (no network, no model calls, no training):

- attack_data manifests (`data.yml` + real event files) supply the known
  malicious types and the leave-one-family-out evaluation instances --
  split by dataset (T.2) so no evaluation artifact's dataset also
  contributed a type.
- The invictus_ir_aws_dataset CloudTrail export supplies the per-environment
  normal baseline (N.2) -- real, but not attack_data, and not the type
  library, per the module docstrings' "known types vs baseline are
  different objects" boundary. It is real IR-case traffic, not a clean
  control; that assumption is reported, not hidden (residual risk, D.0).

Only run after `unit_ladder.run_ladder` and
`unit_ladder.individually_normal_case_surfaces` both report VALID/True --
this script asserts that itself before publishing anything.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from portal.modules.security.core.bully import anchors as anc
from portal.modules.security.core.bully import artifact_graph as ag
from portal.modules.security.core.bully import baseline as bl
from portal.modules.security.core.bully import unit_ladder as ul
from portal.modules.security.core.bully import unit_measurement as um
from portal.modules.security.core.bully import unit_outcome as uo
from scripts.corpus_ingest import (
    coerce,
    iter_cloudtrail_records,
    iter_events_text,
    load_manifest_catalog,
)

ATTACK_DATA_ROOT = Path("/Volumes/data01/portal5_hunt/sources/attack_data/datasets")
BASELINE_ROOT = Path("/Volumes/data01/portal5_hunt/corpora/invictus_ir_aws_dataset/repo/CloudTrail")
MAX_RECORDS_PER_DATASET = 200
MIN_FAMILIES = 8


def _sample_records(path: Path, *, limit: int) -> list[dict[str, Any]]:
    """Real records from one dataset/log file, best-effort (S1): a format
    this can't parse yields fewer records, never an error."""
    out: list[dict[str, Any]] = []
    try:
        for line in iter_events_text(path):
            for record in iter_cloudtrail_records(line):
                parsed = coerce(record) if isinstance(record, str) else record
                if isinstance(parsed, dict):
                    out.append(parsed)
                    if len(out) >= limit:
                        return out
    except OSError:
        return out
    return out


def _dataset_key(path: Path) -> str:
    return str(path)


def _build_type_library(datasets: list[Any]) -> anc.AnchorLibrary:
    library = anc.AnchorLibrary()
    for manifest in datasets:
        records = _sample_records(manifest.path, limit=MAX_RECORDS_PER_DATASET)
        if not records:
            continue
        graph = ag.build_graph(records)
        window_units = [u for u in ag.enumerate_units(graph) if u.level == "L4_WINDOW"]
        action_sequence = list(window_units[0].vocabulary) if window_units else []
        library.load_attack_episode(
            source_id="attack_data",
            record={
                "record_id": f"attack-episode-{_dataset_key(manifest.path)}",
                "action_sequence": action_sequence,
            },
            techniques=manifest.techniques,
        )
    return library


def _eval_unit_for_dataset(manifest: Any) -> ag.GradeableUnit | None:
    records = _sample_records(manifest.path, limit=MAX_RECORDS_PER_DATASET)
    if len(records) < 2:
        return None
    graph = ag.build_graph(records)
    units = [u for u in ag.enumerate_units(graph) if u.level == "L4_WINDOW"]
    return units[0] if units else None


def _build_baseline() -> tuple[bl.NormalBaseline, int, list[ag.GradeableUnit]]:
    """Fit from most of the invictus_ir_aws_dataset CloudTrail export;
    reserve a held-out slice of its files (never touched by `fit`) as the
    benign control for T.4 -- genuinely "normal for this environment"
    instances, not synthetic filler the baseline was never shown."""
    model = bl.NormalBaseline(environment_id="invictus-ir-aws")
    files = sorted(BASELINE_ROOT.glob("*.json")) if BASELINE_ROOT.is_dir() else []
    held_out_count = max(1, len(files) // 5)
    fit_files, held_out_files = files[held_out_count:], files[:held_out_count]

    fit_units: list[ag.GradeableUnit] = []
    for path in fit_files:
        records = _sample_records(path, limit=MAX_RECORDS_PER_DATASET)
        if not records:
            continue
        graph = ag.build_graph(records)
        fit_units.extend(
            u for u in ag.enumerate_units(graph) if u.level in ("L1_ARTIFACT", "L2_ENTITY")
        )
    model.fit(fit_units)

    benign_control_units: list[ag.GradeableUnit] = []
    for path in held_out_files:
        records = _sample_records(path, limit=MAX_RECORDS_PER_DATASET)
        if len(records) < 2:
            continue
        graph = ag.build_graph(records)
        windows = [u for u in ag.enumerate_units(graph) if u.level == "L4_WINDOW"]
        if windows:
            benign_control_units.append(windows[0])
    return model, len(files), benign_control_units


def _confidence_calibration(rows: list[um.GradingPlaneRow]) -> dict[str, Any]:
    scored = [r for r in rows if r.scored and r.outcome.brief is not None]
    if not scored:
        return {"n": 0, "buckets": {}}
    buckets: dict[str, list[bool]] = defaultdict(list)
    for row in scored:
        conf = row.outcome.brief.confidence if row.outcome.brief else 0.0
        bucket = f"{int(conf * 10) * 10}-{int(conf * 10) * 10 + 10}%"
        buckets[bucket].append(row.correct)
    return {
        "n": len(scored),
        "buckets": {
            k: {"n": len(v), "empirical_accuracy": sum(v) / len(v)}
            for k, v in sorted(buckets.items())
        },
    }


def _run_ladder_from_real_vocabulary(
    full_library: anc.AnchorLibrary,
) -> tuple[dict[str, Any] | None, bool]:
    """Real verbs, harvested from the actual type library and grouped by the
    class they classify to, then assembled into a 3-class parent so the
    ladder has real structure to perturb -- searching for one anchor whose
    own first few tokens happen to span multiple classes is unreliable
    against real attack_data (most datasets are single-class recon
    bursts), so the parent is composed explicitly instead."""
    verbs_by_class: dict[str, set[str]] = defaultdict(set)
    for anchor in full_library.all():
        for verb in anchor.record.get("action_sequence") or []:
            verbs_by_class[ag.DEFAULT_ACTION_CLASSIFIER.classify(verb)].add(verb)

    wanted_classes = ("auth", "enumerate", "execute")
    if not all(verbs_by_class.get(c) for c in wanted_classes):
        return None, False

    parent_verbs = [sorted(verbs_by_class[c])[0] for c in wanted_classes]
    substitution_pool = sorted(verbs_by_class["execute"] - {parent_verbs[2]})
    substitution_verb = substitution_pool[0] if substitution_pool else "InvokeFunction"
    rungs = ul.build_rungs(
        parent_verbs,
        substitution_verb=substitution_verb,
        # Real Windows-native verbs (U.3', RC4) -- not the class names
        # themselves. These are not hand-picked to classify perfectly;
        # whatever shape distance results is the honest cross-vocabulary
        # signal, published as-is rather than smoothed toward a clean rung.
        cross_vocabulary_verbs=["Logon", "whoami", "Invoke-Command"],
        unrelated_verbs=["SELECT", "INSERT", "COMMIT"],
    )
    parent_type_record = {"record_id": "ladder-parent", "action_sequence": parent_verbs}
    report = ul.run_ladder(parent_type_record, rungs)
    return report, report["verdict"] == "VALID"


_FLAGSHIP_CHAIN = [
    "AssumeRole",
    "GetSessionToken",
    "AttachUserPolicy",
    "PutBucketPolicy",
    "DeleteBucket",
    "PutObject",
]


def _individually_normal_flagship_case() -> tuple[
    dict[str, Any], anc.AnchorLibrary, bl.NormalBaseline
]:
    def _l1_unit(verb: str, entity: str) -> ag.GradeableUnit:
        records = [{"eventName": verb, "user": entity, "eventTime": 0.0}]
        graph = ag.build_graph(records)
        return next(u for u in ag.enumerate_units(graph) if u.level == "L1_ARTIFACT")

    combo_library = anc.AnchorLibrary()
    combo_baseline = bl.NormalBaseline(environment_id="ci-combo")
    combo_baseline.fit([_l1_unit(v, f"bg-{v}-{i}") for v in _FLAGSHIP_CHAIN for i in range(20)])
    result = ul.individually_normal_case_surfaces(
        _FLAGSHIP_CHAIN, library=combo_library, baseline=combo_baseline
    )
    return result, combo_library, combo_baseline


def _suppression_demo() -> dict[str, Any]:
    library = anc.AnchorLibrary()
    model = bl.NormalBaseline(environment_id="suppression-demo")
    verbs = ["AssumeRole", "ListBuckets", "AttachUserPolicy"]

    def _unit_for(entity: str) -> ag.GradeableUnit:
        records = [
            {"eventName": v, "user": entity, "eventTime": i * 40.0} for i, v in enumerate(verbs)
        ]
        graph = ag.build_graph(records)
        return next(u for u in ag.enumerate_units(graph) if u.level == "L4_WINDOW")

    first_seen = uo.resolve_unit_outcome(_unit_for("first"), list(library.all()), model)
    uo.write_unit_outcome_as_anchor(
        library, first_seen, source_id="analyst", analyst_disposition="BENIGN_CLOSE"
    )
    second_seen = uo.resolve_unit_outcome(_unit_for("second"), list(library.all()), model)
    return {
        "first_sighting_outcome": first_seen.outcome,
        "second_sighting_outcome": second_seen.outcome,
        "suppression_fired": second_seen.outcome == "RECOGNIZED_NORMAL",
    }


def _grade_eval_datasets(
    eval_datasets: list[Any], full_library: anc.AnchorLibrary, baseline: bl.NormalBaseline
) -> tuple[dict[str, list[ag.GradeableUnit]], list[um.GradingPlaneRow], list[uo.UnitOutcome], int]:
    eval_units_by_family: dict[str, list[ag.GradeableUnit]] = defaultdict(list)
    grading_rows: list[um.GradingPlaneRow] = []
    all_outcomes: list[uo.UnitOutcome] = []
    unconnected = 0
    for m in eval_datasets:
        unit = _eval_unit_for_dataset(m)
        if unit is None:
            unconnected += 1
            continue
        family = m.techniques[0]
        eval_units_by_family[family].append(unit)
        outcome = uo.resolve_unit_outcome(unit, list(full_library.all()), baseline)
        all_outcomes.append(outcome)
        grading_rows.append(um.bind_ground_truth(outcome, family=family, malice="malicious"))
    return eval_units_by_family, grading_rows, all_outcomes, unconnected


_CREDENTIAL_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r'accessKeyId=[^"\\\s]+'),
)


def _redact_credentials(text: str) -> str:
    """attack_data/invictus_ir_aws_dataset are public example datasets, but
    their sample events still carry AWS-access-key-shaped tokens
    (`accessKeyId`) that a secret scanner correctly flags on sight -- this
    report only ever needs the *fact* that an entity token existed, never
    its literal value, so every such token is redacted before anything is
    written to disk."""
    redacted = text
    for pattern in _CREDENTIAL_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    path.write_text(_redact_credentials(text))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split-seed", type=int, default=0)
    parser.add_argument(
        "--output", type=Path, default=Path("docs/BULLY_UNKNOWN_COUSIN_RUN_M3_V1.json")
    )
    args = parser.parse_args()

    manifests = [
        m for m in load_manifest_catalog(ATTACK_DATA_ROOT) if m.techniques and m.path.is_file()
    ]
    dataset_keys = [_dataset_key(m.path) for m in manifests]
    split = um.split_datasets(dataset_keys, type_fraction=0.5, seed=args.split_seed)

    type_datasets = [m for m in manifests if _dataset_key(m.path) in split.type_dataset_keys]
    eval_datasets = [m for m in manifests if _dataset_key(m.path) in split.eval_dataset_keys]
    um.assert_no_contamination([_dataset_key(m.path) for m in eval_datasets], split)

    full_library = _build_type_library(type_datasets)
    baseline, baseline_file_count, benign_control_units = _build_baseline()

    # -- M.1: falsification instrument, gate on VALID before anything else --
    ladder_report, ladder_valid = _run_ladder_from_real_vocabulary(full_library)
    individually_normal, combo_library, combo_baseline = _individually_normal_flagship_case()

    if not (ladder_valid and individually_normal["passes"]):
        payload = {
            "schema": "BULLY_UNKNOWN_COUSIN_RUN_M3_V1",
            "verdict": "INVALID",
            "reason": "M.1 falsification instrument did not report VALID; run aborted before publishing.",
            "ladder_report": ladder_report,
            "individually_normal_case": individually_normal,
        }
        _write_json(args.output, payload)
        print(json.dumps({"output": str(args.output), "verdict": "INVALID"}, sort_keys=True))
        return 1

    # -- grading-plane rows over the held-out evaluation datasets --
    eval_units_by_family, grading_rows, all_outcomes, unconnected = _grade_eval_datasets(
        eval_datasets, full_library, baseline
    )
    families_with_units = {f: units for f, units in eval_units_by_family.items() if units}
    library_by_family: dict[str, list[anc.Anchor]] = defaultdict(list)
    for anchor in full_library.all():
        techniques = [
            t.get("technique_id") if isinstance(t, dict) else t
            for t in (anchor.record.get("attack_mappings") or [])
        ]
        for t in techniques:
            library_by_family[t].append(anchor)

    lofo_report: dict[str, Any] | None = None
    if len(families_with_units) >= MIN_FAMILIES:
        lofo = um.run_leave_one_family_out(
            families_with_units,
            library_by_family,
            list(full_library.all()),
            baseline,
            benign_eval_units=benign_control_units,
        )
        lofo_report = lofo.to_dict()

    precision_recall = um.precision_recall_report(grading_rows)
    calibration = _confidence_calibration(grading_rows)

    # -- suppression evidence (L.1) --
    suppression_evidence = _suppression_demo()

    # -- concern briefs, flagship first --
    concern_outcomes = [o for o in all_outcomes if o.brief is not None]
    flagship_outcome = uo.resolve_unit_outcome(
        ul.unit_from_verbs(_FLAGSHIP_CHAIN, entity="flagship"),
        list(combo_library.all()),
        combo_baseline,
    )
    briefs = []
    if flagship_outcome.brief is not None:
        briefs.append(
            {**flagship_outcome.brief.to_dict(), "flagship_individually_unremarkable_combo": True}
        )
    briefs.extend(o.brief.to_dict() for o in concern_outcomes[:9] if o.brief is not None)

    outcome_distribution_by_level: dict[str, dict[str, int]] = defaultdict(Counter)
    for o in all_outcomes:
        outcome_distribution_by_level[o.unit.level][o.outcome] += 1

    distances = [
        d
        for o in all_outcomes
        if o.relation is not None
        for d in (o.relation.shape.distance, o.relation.vocabulary.distance)
        if d is not None
    ]
    remarkabilities = [o.remarkability for o in all_outcomes]

    payload: dict[str, Any] = {
        "schema": "BULLY_UNKNOWN_COUSIN_RUN_M3_V1",
        "cold": True,
        "split_seed": args.split_seed,
        "manifest_count": len(manifests),
        "type_dataset_count": len(type_datasets),
        "eval_dataset_count": len(eval_datasets),
        "baseline_source_file_count": baseline_file_count,
        "baseline_fitted_units": baseline.fitted_units,
        "ladder_report": ladder_report,
        "individually_normal_case": individually_normal,
        "leave_one_family_out": lofo_report,
        "leave_one_family_out_benign_control_note": (
            "The benign control is drawn from a held-out slice of the "
            "invictus_ir_aws_dataset CloudTrail export -- the only local "
            "corpus available outside attack_data. That dataset is itself a "
            "real incident-response case study (stratus-red-team simulated "
            "intrusion activity present throughout), not clean traffic, so "
            "a high benign_control_concern_rate here is the residual risk "
            "'the baseline can be poisoned by an adversary present "
            "throughout the fitting window' (D.0) actually manifesting, "
            "not a grading bug. Reported honestly rather than swapped for "
            "a synthetic corpus that would pass the control artificially."
        ),
        "precision_recall": precision_recall,
        "confidence_calibration": calibration,
        "outcome_distribution_by_level": {
            k: dict(v) for k, v in outcome_distribution_by_level.items()
        },
        "distance_distribution": {
            "mean": statistics.fmean(distances) if distances else None,
            "median": statistics.median(distances) if distances else None,
        },
        "remarkability_distribution": {
            "mean": statistics.fmean(remarkabilities) if remarkabilities else None,
            "median": statistics.median(remarkabilities) if remarkabilities else None,
        },
        "suppression_evidence": suppression_evidence,
        "unconnected_artifact_count": unconnected,
        "unconnected_artifact_rate": unconnected / len(eval_datasets) if eval_datasets else 0.0,
        "concern_briefs": briefs,
        "concern_brief_count": len(briefs),
        "families_evaluated": sorted(families_with_units),
        "coverage_gap_note": (
            "unconnected_artifact_rate is the honest bound on structural grouping: an "
            "attack spread across entities with no shared key/causal link is missed by "
            "the graph, not silently marked NORMAL."
        ),
    }

    _write_json(args.output, payload)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "families_evaluated": len(families_with_units),
                "unknown_cousin_recall": (lofo_report or {}).get("unknown_cousin_recall"),
                "full_library_recall": (lofo_report or {}).get("full_library_recall"),
                "concern_brief_count": len(briefs),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
