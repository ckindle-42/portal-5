"""Tests for the live orchestration suite runner against its fake Pipeline."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "unit"))

from orchestration_fake_pipeline import (  # noqa: E402
    FakePipeline,
    text_response,
    tool_response,
)

from portal.platform.inference.router import auth  # noqa: E402
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
            api_key=auth.PIPELINE_API_KEY,
            dry_run=dry_run,
        )


def test_detection_bite_pipeline_tools_are_auto_spl_workspace_tools() -> None:
    config = yaml.safe_load((ROOT / "config/portal.yaml").read_text(encoding="utf-8"))
    workspace_tools = set(config["workspaces"]["auto-spl"]["tools"])
    cases = runner.load_suite(
        ROOT / "portal/modules/orchestration/disciplines/detection_engineering/wfe_bites.yaml"
    )
    local_tools = set(runner.READ_TOOLS) | set(runner.ACTION_TOOLS)
    pipeline_tools = {name for case in cases for name in case["tools"]} - local_tools
    assert pipeline_tools <= workspace_tools


def test_suite_engine_identifies_as_an_api_client() -> None:
    engine = runner.SuiteEngine("bench-spark-x26", "http://localhost")
    assert engine._headers()["X-Portal-Client"] == "api"


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

    # Each case-repeat sends its bite request plus one finish-repair turn for
    # the fake's default text-only reply.
    assert len(pipeline.requests) == 16
    assert all(row["model"] == "bench-spark-x26" for row in pipeline.requests)
    assert all(row["exec_audit"] is True for row in pipeline.requests)
    assert all("finish" in row["portal_bite_tools"] for row in pipeline.requests)
    # The discipline's tool persona, as production sends it; without it the Pipeline offers
    # the seat's own pool and every detection tool goes missing (10-23 HARNESS_ERROR).
    assert all(row["portal_bite_persona"] == "splunkdetectionauthor" for row in pipeline.requests)
    for request in pipeline.requests:
        finish = next(tool for tool in request["tools"] if tool["function"]["name"] == "finish")
        parameters = finish["function"]["parameters"]
        assert parameters["required"] == ["output"]
        assert "output_path" not in parameters["properties"]
    assert all("chat_template_kwargs" not in row for row in pipeline.requests)
    assert all(
        [tool["function"]["name"] for tool in row["tools"]] == row["portal_bite_tools"]
        for row in pipeline.requests
    )
    assert receipt["gate_evidence"] is False
    assert all(row["state"] == "running" for row in receipt["results"])
    run_dir = Path(receipt["workdir"])
    assert (run_dir / "plan.json").is_file()
    assert (run_dir / "receipt.json").is_file()


def test_testfix_bite_suite_splits_reading_and_action_tools(tmp_path: Path):
    case = runner.load_suite(ROOT / "tests/wfe/suites/orchestration_test_fixing.jsonl")[0]
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    bite, input_paths = runner._bite_contract(case, "test_fixing", task_dir, dry_run=True)

    stages = runner._stage_bites(bite, input_paths, task_dir)

    assert [stage.tools for stage, _inputs in stages] == [
        ("file_read",),
        ("file_write", "pytest_run"),
    ]
    assert stages[0][0].reads_untrusted
    assert not stages[1][0].reads_untrusted
    assert stages[1][0].write_paths == ("clamp.py",)
    assert stages[1][1] == {
        "clamp.py": Path("clamp.py"),
        "test_clamp.py": Path("test_clamp.py"),
        "inspection": Path(stages[0][0].output_path),
    }


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


def test_planner_judge_valid_split_plan_is_valid_by_accept_and_rules_say_so(
    tmp_path: Path,
) -> None:
    """Deep REJECTed valid-split-plan for a missing review_reason on its deep final_review
    (2026-10-28); the bite is valid through its accept check, and the rules now say so."""
    config = yaml.safe_load((ROOT / "config/orchestration_arm.yaml").read_text(encoding="utf-8"))
    cases = runner.load_suite(
        ROOT / "portal/modules/orchestration/disciplines/detection_engineering/wfe_planner.yaml"
    )
    valid_messages = None
    for case in cases:
        task_dir = tmp_path / runner._safe_name(case["id"])
        task_dir.mkdir()
        # Raises if the validator verdict differs from the fixture's expected verdict.
        messages = runner._planner_messages(case, config, "detection-engineering", task_dir)
        if case["id"] == "valid-split-plan":
            valid_messages = messages
    assert valid_messages is not None
    user = json.loads(next(m["content"] for m in valid_messages if m["role"] == "user"))
    final_review = user["plan"]["bites"][-1]
    assert final_review["bite_id"] == "final_review"
    assert final_review["model"] == "deep" and final_review["accept"]
    system = next(m["content"] for m in valid_messages if m["role"] == "system")
    assert "a bite with accept checks needs no review_reason, whatever its model" in system


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
        for _ in range(2):
            response = tool_response(
                "finish",
                json.dumps({"output": good["artifact"], "output_path": "bite-output.json"}),
            )
            # The pipeline-internal call shape _exec_audit_event converts —
            # not the SSE event shape it emits.
            response["exec_audit"] = [
                {
                    "function": {"name": call["name"], "arguments": json.dumps(call["args"])},
                    "_output": json.dumps(call["output"]),
                }
                for call in good["calls"]
            ]
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
                api_key=auth.PIPELINE_API_KEY,
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
            api_key=auth.PIPELINE_API_KEY,
        )
    finally:
        pipeline.close()

    row = receipt["results"][0]
    assert row["state"] == "harness_error"
    assert row["status"] == "HARNESS_ERROR"
    assert "unparsed tool-call markup" in row["evidence"]["error"]
    assert pipeline.requests[0]["portal_bite_tools"] == ["file_read", "finish"]
    assert [tool["function"]["name"] for tool in pipeline.requests[0]["tools"]] == [
        "file_read",
        "finish",
    ]
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
                api_key=auth.PIPELINE_API_KEY,
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


def test_checker_messages_state_the_exact_artifact_contract() -> None:
    fixture = {
        "checker": {"type": "spl_syntax", "artifact_field": "spl"},
        "artifact": {},
        "calls": [],
    }
    messages = runner._checker_messages({"id": "spl_syntax"}, "fail", fixture)
    system = next(m["content"] for m in messages if m["role"] == "system")
    assert "only when a call to its tool used exactly the artifact's" in system
    assert "validating different content does not validate the artifact" in system


def _json_reply(
    pipeline: FakePipeline, tmp_path: Path, content: str, label: str, name: str
) -> dict:
    pipeline.add_model("bench-spark-x26", text_response(content))
    engine = runner.SuiteEngine("bench-spark-x26", pipeline.url, auth.PIPELINE_API_KEY)
    task_dir = tmp_path / name
    task_dir.mkdir()
    return runner._run_one(
        engine=engine,
        seat="bench-spark-x26",
        discipline="detection-engineering",
        suite="checker",
        case={"id": name},
        label=label,
        messages=[{"role": "user", "content": "judge"}],
        tools=[],
        task_dir=task_dir,
        dry_run=False,
    )


def test_invalid_model_json_is_a_scored_fail_and_only_a_json_fence_parses(tmp_path: Path):
    # Planner r3: a JSON object whose reason string contains raw quotes.
    broken = (
        '{\n  "verdict": "REJECT",\n'
        '  "reason": "The research bite\'s goal says "Read reference.spl". Missing review_reason."\n}'
    )
    # Checker exact-spl-validation fail r1/r2: tool-call markup, then a JSON object.
    tool_then_json = (
        "<tool_call>\n\n\n\n"
        '{"verdict": "PASS", "reason": "spl_validate_syntax returned ok=true with no errors."}'
    )
    # Checker exact-yara-compilation pass r2: a tool call and no JSON object.
    tool_only = (
        "<tool_call>\n"
        '<|im_start|>function=search_web(depth: 1, query: "YARA rule syntax strings condition")'
    )
    fenced_pass = '```json\n{"verdict": "PASS", "reason": "ok"}\n```'
    fenced_reject = '```json\n{"verdict": "REJECT", "reason": "no"}\n```'
    prose_around_fence = 'Looks good.\n```json\n{"verdict": "PASS"}\n```'
    pipeline = FakePipeline()
    try:
        broken_row = _json_reply(pipeline, tmp_path, broken, "pass", "broken-json")
        prefixed_row = _json_reply(pipeline, tmp_path, tool_then_json, "pass", "tool-then-json")
        tool_row = _json_reply(pipeline, tmp_path, tool_only, "pass", "tool-only")
        prose_row = _json_reply(pipeline, tmp_path, prose_around_fence, "pass", "prose-fence")
        bare_row = _json_reply(
            pipeline, tmp_path, json.dumps({"verdict": "MAYBE"}), "pass", "no-verdict"
        )
        fenced_pass_row = _json_reply(pipeline, tmp_path, fenced_pass, "pass", "fenced-pass")
        fenced_reject_row = _json_reply(pipeline, tmp_path, fenced_reject, "pass", "fenced-reject")
        empty_row = _json_reply(pipeline, tmp_path, "", "fail", "empty")
        plain_row = _json_reply(
            pipeline, tmp_path, json.dumps({"verdict": "REJECT"}), "fail", "plain-reject"
        )
    finally:
        pipeline.close()

    assert broken_row["status"] == "FAIL"
    assert broken_row["state"] == "failed"
    assert "Expecting ',' delimiter" in broken_row["evidence"]["error"]
    assert "observed" not in broken_row["evidence"]
    # Inner verdict is PASS, which would satisfy a pass label if the prefix were stripped.
    assert prefixed_row["status"] == "FAIL"
    assert prefixed_row["evidence"]["error"].startswith("JSONDecodeError:")
    assert "observed" not in prefixed_row["evidence"]
    assert tool_row["status"] == "FAIL"
    assert tool_row["evidence"]["error"].startswith("JSONDecodeError:")
    assert prose_row["status"] == "FAIL"
    assert "observed" not in prose_row["evidence"]
    assert bare_row["status"] == "FAIL"
    assert bare_row["evidence"]["error"].startswith("ValueError:")
    assert fenced_pass_row["status"] == "PASS"
    assert fenced_pass_row["evidence"] == {"expected": "PASS", "observed": "PASS"}
    assert fenced_reject_row["status"] == "FAIL"
    assert fenced_reject_row["evidence"] == {"expected": "PASS", "observed": "REJECT"}
    assert empty_row["status"] == "BLOCKED"
    assert empty_row["state"] == "blocked"
    assert empty_row["evidence"] == {"error": "empty model content"}
    assert plain_row["status"] == "PASS"
    assert plain_row["evidence"] == {"expected": "REJECT", "observed": "REJECT"}
    assert all(row["response_format"] == {"type": "json_object"} for row in pipeline.requests)
    assert all(row["portal_no_tools"] is True for row in pipeline.requests)


def test_planner_and_checker_requests_carry_the_production_output_budget():
    """A json_output (planner/checker) request sends plan_goal's max_tokens, not the seat default."""
    body = runner._request_body(
        "auto-daily::gemma-fast", [{"role": "user", "content": "x"}], [], json_output=True
    )
    assert body["max_tokens"] == runner.PLANNER_MAX_TOKENS == 8192
