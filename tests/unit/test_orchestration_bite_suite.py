"""Tests for the live orchestration suite runner against its fake Pipeline."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "unit"))

from orchestration_fake_pipeline import (  # noqa: E402
    FakePipeline,
    text_response,
    tool_response,
)

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
    with patch.dict(os.environ, {"AI_OUTPUT_DIR": str(tmp_path)}):
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
    assert all("finish" in row["portal_bite_tools"] for row in pipeline.requests)
    assert all(row["chat_template_kwargs"]["enable_thinking"] is True for row in pipeline.requests)
    assert all(row["tools"][0]["function"]["name"] == "finish" for row in pipeline.requests)
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
            response = tool_response(
                "finish",
                json.dumps({"output": good["artifact"], "output_path": "bite-output.json"}),
            )
            response["exec_audit"] = audit
            pipeline.add_model("bench-spark-x26", response)
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


def test_missing_tools_in_pipeline_trace_is_a_harness_error_and_gate_c_skips_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    pipeline = FakePipeline()
    pipeline.offered_tools_override = []
    cases = runner.load_suite(
        ROOT / "portal/modules/orchestration/disciplines/detection_engineering/wfe_bites.yaml"
    )
    suite_path = tmp_path / "bite.jsonl"
    suite_path.write_text(json.dumps(cases[0]) + "\n", encoding="utf-8")
    pipeline.add_model("bench-spark-x26", text_response("no finish call"))
    monkeypatch.setattr(runner, "_selected_suites", lambda *_args: {"bite": suite_path})
    try:
        with patch.dict(os.environ, {"AI_OUTPUT_DIR": str(tmp_path)}):
            receipt = runner.run_trial(
                config_path=ROOT / "config/orchestration_arm.yaml",
                discipline="detection-engineering",
                seat="bench-spark-x26",
                suite="bite",
                repeats=1,
                output_dir=tmp_path,
                pipeline_url=pipeline.url,
            )
    finally:
        pipeline.close()

    row = receipt["results"][0]
    assert row["state"] == "harness_error"
    assert row["status"] == "HARNESS_ERROR"
    assert "bite tool" in row["evidence"]["error"]
    assert receipt["status"] == "HARNESS_ERROR"
    assert extract_discipline_rates([receipt]) == {}


def test_replayed_calibration_markup_is_a_harness_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    pipeline = FakePipeline()
    evidence = (ROOT / "tests/fixtures/orchestration/deep_clamp_response_20261022.txt").read_text(
        encoding="utf-8"
    )
    pipeline.add_model("auto-daily::deep", text_response(evidence))
    case_text = (ROOT / "tests/wfe/suites/orchestration_test_fixing.jsonl").read_text()
    case = json.loads(case_text.splitlines()[0])
    suite_path = tmp_path / "bite.jsonl"
    suite_path.write_text(json.dumps(case) + "\n", encoding="utf-8")
    monkeypatch.setenv("AI_OUTPUT_DIR", str(tmp_path / "AI_Output"))
    monkeypatch.setattr(runner, "_selected_suites", lambda *_args: {"bite": suite_path})
    try:
        receipt = runner.run_trial(
            config_path=ROOT / "config/orchestration_arm.yaml",
            discipline="test_fixing",
            seat="auto-daily::deep",
            suite="bite",
            repeats=1,
            output_dir=tmp_path / "AI_Output" / "generated" / "tasks",
            pipeline_url=pipeline.url,
        )
    finally:
        pipeline.close()

    row = receipt["results"][0]
    assert row["state"] == "harness_error"
    assert row["status"] == "HARNESS_ERROR"
    assert "unparsed tool-call markup" in row["evidence"]["error"]
    assert set(pipeline.requests[0]["portal_bite_tools"]) == {
        "file_read",
        "file_write",
        "pytest_run",
        "finish",
    }
    assert pipeline.requests[0]["tools"][0]["function"]["name"] == "finish"
    assert "read_word_document" not in pipeline.requests[0]["portal_bite_tools"]
    assert extract_discipline_rates([receipt]) == {}


def test_bite_worker_rejects_missing_allowlist_before_sending_request():
    pipeline = FakePipeline()
    engine = runner.SuiteEngine("bench-spark-x26", pipeline.url)
    engine.expected_bite_tools = ("file_read", "finish")
    try:
        with pytest.raises(runner.HarnessError, match="missing tools"):
            engine.chat({"model": "bench-spark-x26", "tools": []}, 1, lambda _event: None)
        assert pipeline.requests == []
    finally:
        pipeline.close()


def test_all_suite_clears_bite_guard_before_the_planner_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    pipeline = FakePipeline()
    bite_case = {
        "id": "small-artifact",
        "goal": "Return a small artifact.",
        "tools": [],
        "artifact_schema": {
            "type": "object",
            "required": ["answer"],
            "properties": {"answer": {"type": "string"}},
        },
    }
    bite_path = tmp_path / "bite.jsonl"
    bite_path.write_text(json.dumps(bite_case) + "\n", encoding="utf-8")
    planner_path = tmp_path / "planner.yaml"
    planner_path.write_text(
        "cases:\n  - id: valid-small-plan\n    expected: pass\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        runner,
        "_selected_suites",
        lambda *_args: {"bite": bite_path, "planner": planner_path},
    )
    output = {"output": {"answer": "ok"}, "output_path": "bite-output.json"}
    pipeline.add_model("bench-spark-x26", tool_response("finish", json.dumps(output)))
    pipeline.add_model("bench-spark-x26", text_response(json.dumps({"verdict": "PASS"})))
    try:
        with patch.dict(os.environ, {"AI_OUTPUT_DIR": str(tmp_path)}):
            receipt = runner.run_trial(
                config_path=ROOT / "config/orchestration_arm.yaml",
                discipline="test_fixing",
                seat="bench-spark-x26",
                suite="all",
                repeats=1,
                output_dir=tmp_path,
                pipeline_url=pipeline.url,
            )
    finally:
        pipeline.close()

    assert [row["status"] for row in receipt["results"]] == ["PASS", "PASS"]
    assert "portal_bite_tools" in pipeline.requests[0]
    assert "portal_bite_tools" not in pipeline.requests[1]


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
