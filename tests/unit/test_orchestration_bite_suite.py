"""Tests for the live orchestration suite runner against its fake Pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT / "tests" / "unit"))

from orchestration_fake_pipeline import (  # noqa: E402
    FakePipeline,
)

from scripts import orchestration_bite_suite as runner  # noqa: E402


def test_suite_engine_identifies_as_an_api_client() -> None:
    engine = runner.SuiteEngine("bench-spark-x26", "http://localhost")
    assert engine._headers()["X-Portal-Client"] == "api"


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


def test_planner_and_checker_requests_carry_the_production_output_budget():
    """A json_output (planner/checker) request sends plan_goal's max_tokens, not the seat default."""
    body = runner._request_body(
        "auto-daily::gemma-fast", [{"role": "user", "content": "x"}], [], json_output=True
    )
    assert body["max_tokens"] == runner.PLANNER_MAX_TOKENS == 8192
