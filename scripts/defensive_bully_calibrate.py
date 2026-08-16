#!/usr/bin/env python3
"""Run the P6.8 cousin-calibration bench on an isolated Organ snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from portal.modules.security.core.bully import config as bully_config  # noqa: E402
from portal.modules.security.core.bully.class_onboarding import (  # noqa: E402
    V3_SCOPE,
    class_verdict,
    compare_v3_regression,
    run_cross_class_acceptance,
    run_detection_qa,
    v3_profile_from_artifact,
    write_loop_record,
)
from portal.modules.security.core.bully.cousin_calibration_bench import (  # noqa: E402
    corpus_parent_reference_record,
    load_specimen_corpus,
    run_baseline_bench,
    run_class_cohort_bench,
    run_source_scope_bench,
)
from portal.modules.security.core.bully.organ import Organ  # noqa: E402
from portal.modules.security.core.bully.specimen_ledger import SpecimenLedger  # noqa: E402
from portal.modules.security.core.bully.store import Store  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--ledger-root", type=Path)
    parser.add_argument(
        "--cohort",
        action="append",
        default=[],
        help="characterize exactly this source class (repeatable)",
    )
    parser.add_argument(
        "--cross-class",
        action="store_true",
        help="run SA1 X1-X5 on the same mixed parent snapshot",
    )
    parser.add_argument(
        "--v3-regression-baseline",
        type=Path,
        help="compare the current four-class scope against this frozen V3 report",
    )
    parser.add_argument(
        "--detection-qa",
        action="append",
        default=[],
        metavar="SOURCE=TECHNIQUE",
        help="run live-positive/benign QA for an admitted class (repeatable)",
    )
    return parser


def _source_techniques(values: list[str]) -> dict[str, str]:
    parsed = {}
    for item in values:
        source_class, separator, technique_id = item.partition("=")
        if not separator or not source_class or not technique_id:
            raise ValueError(f"invalid --detection-qa value: {item!r}")
        parsed[source_class] = technique_id
    return parsed


def _seed_parents(snapshot: Organ, corpus: dict) -> int:
    records = [
        corpus_parent_reference_record(parent)
        for parent in corpus["specimens"]
        if parent["source_lane"] == "attack_data"
    ]
    seeded = snapshot.stats()["row_count"]
    if seeded == 0:
        snapshot.upsert_many(records, batch_size=16)
        return snapshot.stats()["row_count"]
    if seeded != len(records):
        raise RuntimeError(
            "existing calibration snapshot has an unexpected row count; use a fresh output directory"
        )
    return seeded


def _run_cohorts(snapshot, args, corpus_path, ledger, output_dir):
    reports = {}
    for source_class in args.cohort:
        safe_name = source_class.replace(":", "_").replace("/", "_")
        reports[source_class] = run_class_cohort_bench(
            snapshot,
            source_class=source_class,
            corpus_path=corpus_path,
            ledger=ledger,
            output_dir=output_dir / "cohorts" / safe_name,
        )
    if reports:
        return reports, next(iter(reports.values()))
    return reports, run_baseline_bench(
        snapshot, corpus_path=corpus_path, ledger=ledger, output_dir=output_dir
    )


def _run_regression(snapshot, baseline, corpus_path, ledger, output_dir):
    if not baseline:
        return None
    report = run_source_scope_bench(
        snapshot,
        source_classes=V3_SCOPE,
        corpus_path=corpus_path,
        ledger=ledger,
        output_dir=output_dir / "v3_regression",
    )
    comparison = compare_v3_regression(report, baseline)
    (output_dir / "v3_regression" / "regression_comparison.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return comparison


def _run_snapshot(snapshot, args, corpus, corpus_path, ledger, output_dir, detection_qa):
    seeded_rows = _seed_parents(snapshot, corpus)
    cohort_reports, report = _run_cohorts(snapshot, args, corpus_path, ledger, output_dir)
    cross_class = (
        run_cross_class_acceptance(
            snapshot,
            corpus=corpus,
            output_path=output_dir / "cross_class_acceptance.json",
        )
        if args.cross_class
        else None
    )
    regression = _run_regression(
        snapshot,
        args.v3_regression_baseline,
        corpus_path,
        ledger,
        output_dir,
    )
    if cohort_reports and cross_class and regression and detection_qa:
        profile = v3_profile_from_artifact(args.v3_regression_baseline)
        write_loop_record(
            output_dir / "class_onboarding_v1.json",
            verdicts=[
                class_verdict(source_class, cohort_report, v3_profile=profile)
                for source_class, cohort_report in cohort_reports.items()
            ],
            regression=regression,
            cross_class=cross_class,
            corpus=corpus,
            detection_qa=detection_qa,
        )
    return {
        "report": report,
        "cohort_reports": cohort_reports,
        "cross_class": cross_class,
        "regression": regression,
        "seeded_rows": seeded_rows,
        "final_rows": snapshot.stats()["row_count"],
    }


def _emit_result(run, detection_qa, output_dir) -> int:
    report = run["report"]
    cohorts = run["cohort_reports"]
    result = {
        "passed": report.passed,
        "status": report.status,
        "controls": report.controls,
        "output_dir": str(output_dir),
        "seeded_parent_rows": run["seeded_rows"],
        "final_snapshot_rows": run["final_rows"],
        "children_indexed": run["final_rows"] - run["seeded_rows"],
        "calibration_proposal": report.calibration_proposal,
        "cohorts": {
            source: {
                "status": item.status,
                "controls_passed": bool(item.controls.get("passed")),
            }
            for source, item in cohorts.items()
        },
        "cross_class_passed": run["cross_class"] and run["cross_class"]["passed"],
        "v3_regression": run["regression"],
        "detection_qa_passed": detection_qa and detection_qa["passed"],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    checks = [report.status == "VALID", *(item.status == "VALID" for item in cohorts.values())]
    checks.extend(
        value["passed"]
        for value in (run["cross_class"], run["regression"], detection_qa)
        if value is not None
    )
    return 0 if all(checks) else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    run_id = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or (bully_config.hunt_dir() / "artifacts" / "calibration" / run_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = args.corpus or (
        bully_config.hunt_dir() / "artifacts" / "specimen_corpus_v2" / "specimen_corpus_v2.json"
    )
    ledger = SpecimenLedger(args.ledger_root or bully_config.hunt_dir() / "specimens")
    corpus = load_specimen_corpus(corpus_path)
    if ledger.snapshot_hash() != corpus["ledger_snapshot_hash"]:
        raise ValueError("specimen corpus and sealed ledger snapshot do not match")
    source_techniques = _source_techniques(args.detection_qa)
    detection_qa = (
        run_detection_qa(
            corpus,
            source_techniques=source_techniques,
            output_path=output_dir / "detection_qa.json",
        )
        if source_techniques
        else None
    )

    with Store(output_dir / "snapshot_state.db") as store:
        snapshot = Organ(
            store=store,
            db_path=output_dir / "organ_snapshot",
            embed_client=httpx.Client(timeout=600.0),
        )
        try:
            run = _run_snapshot(
                snapshot, args, corpus, corpus_path, ledger, output_dir, detection_qa
            )
        finally:
            snapshot.close()
    return _emit_result(run, detection_qa, output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
