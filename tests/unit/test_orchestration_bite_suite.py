"""Tests for the live orchestration suite runner against its fake Pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "unit"))

from orchestration_fake_pipeline import FakePipeline, text_response  # noqa: E402

from scripts import orchestration_bite_suite as runner  # noqa: E402
from scripts.gate_c_calculator import (  # noqa: E402
    compute_gate_c_threshold,
    extract_discipline_rates,
)


def _trial(
    pipeline: FakePipeline,
    tmp_path: Path,
    *,
    discipline: str,
    suite: str,
    repeats: int = 1,
    dry_run: bool = False,
) -> dict:
    return runner.run_trial(
        config_path=ROOT / "config/orchestration_arm.yaml",
        discipline=discipline,
        seat="bench-spark-x26",
        suite=suite,
        repeats=repeats,
        output_dir=tmp_path,
        pipeline_url=pipeline.url,
        dry_run=dry_run,
    )


def test_bite_dry_run_sends_one_sequential_request_per_case_and_repeat(tmp_path: Path):
    pipeline = FakePipeline()
    try:
        receipt = _trial(
            pipeline,
            tmp_path,
            discipline="detection-engineering",
            suite="bite",
            repeats=2,
            dry_run=True,
        )
    finally:
        pipeline.close()

    assert len(pipeline.requests) == 8
    assert all(row["model"] == "bench-spark-x26" for row in pipeline.requests)
    assert all(row["exec_audit"] is True for row in pipeline.requests)
    assert receipt["gate_evidence"] is False
    assert all(row["state"] == "running" for row in receipt["results"])
    run_dir = Path(receipt["workdir"])
    assert (run_dir / "plan.json").is_file()
    assert (run_dir / "receipt.json").is_file()


def test_planner_suite_uses_live_pipeline_identity_and_stays_out_of_gate_c(tmp_path: Path):
    pipeline = FakePipeline()
    cases = runner.load_suite(ROOT / "tests/wfe/orchestration/planner_suite.yaml")
    for case in cases:
        verdict = "PASS" if case["expected"] == "pass" else "REJECT"
        pipeline.add_model("bench-spark-x26", text_response(json.dumps({"verdict": verdict})))
    try:
        receipt = _trial(
            pipeline,
            tmp_path,
            discipline="test_fixing",
            suite="planner",
        )
    finally:
        pipeline.close()

    assert receipt["status"] == "PASS"
    assert len(pipeline.requests) == len(cases)
    assert all(row["portal_no_tools"] is True for row in pipeline.requests)
    assert all(item["served"]["workspace"] == "bench-spark-x26" for item in receipt["results"])
    assert extract_discipline_rates([receipt]) == {}


def test_live_bite_receipts_feed_gate_c_with_the_chosen_seat(tmp_path: Path):
    pipeline = FakePipeline()
    cases = runner.load_suite(
        ROOT / "portal/modules/orchestration/disciplines/detection_engineering/wfe_bites.yaml"
    )
    controls = runner.load_suite(
        ROOT
        / "portal/modules/orchestration/disciplines/detection_engineering/wfe_checker_controls.yaml"
    )
    controls_by_id = {item["id"]: item for item in controls}
    for case in cases:
        control = controls_by_id[case["checker"]["type"]]
        good = control["pass"]
        audit = [
            {
                "tool": call["name"],
                "arguments": json.dumps(call["args"]),
                "output": json.dumps(call["output"]),
            }
            for call in good["calls"]
        ]
        for _ in range(2):
            pipeline.add_model(
                "bench-spark-x26",
                text_response(json.dumps(good["artifact"]), exec_audit=audit),
            )
    try:
        receipt = _trial(
            pipeline,
            tmp_path,
            discipline="detection-engineering",
            suite="bite",
            repeats=2,
        )
    finally:
        pipeline.close()

    assert receipt["status"] == "PASS"
    assert len(receipt["results"]) == 8
    assert extract_discipline_rates([receipt]) == {
        "detection-engineering": {"bench-spark-x26": (8, 8)}
    }
    threshold, details = compute_gate_c_threshold(
        [receipt], minimum_samples=5, config_path=ROOT / "config/orchestration_arm.yaml"
    )
    assert threshold > 0
    assert details["pass_criteria_met"] is True


def test_checker_suite_scores_control_pairs_without_counting_them_as_bites(tmp_path: Path):
    pipeline = FakePipeline()
    for label in ("PASS", "REJECT") * 4:
        pipeline.add_model("bench-spark-x26", text_response(json.dumps({"verdict": label})))
    try:
        receipt = _trial(
            pipeline,
            tmp_path,
            discipline="detection-engineering",
            suite="checker",
        )
    finally:
        pipeline.close()

    assert receipt["status"] == "PASS"
    assert len(pipeline.requests) == 8
    assert all(row["portal_no_tools"] is True for row in pipeline.requests)
    assert extract_discipline_rates([receipt]) == {}
