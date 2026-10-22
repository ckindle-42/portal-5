#!/usr/bin/env python3
"""Orchestration arm acceptance harness.

Runs the offline smoke scenarios against the fake Pipeline rig, and the live
wiring checks that need a real Pipeline endpoint. One request at a time; live
mode refuses to start while a WFE sweep is registered or running.

This harness is **not Gate B/C exit evidence**. Live mode covers only the happy
path; every scenario that needs controllable model output or process signals
reports `SKIP` with `required: true`, so a run without that evidence exits
non-zero instead of claiming a green gate.

Usage:
  uv run python scripts/orchestration_acceptance.py --dry-run
  uv run python scripts/orchestration_acceptance.py          # live against :9099
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests" / "unit")]

from orchestration_fake_pipeline import (  # noqa: E402
    FakePipeline,
    SignalResponse,
    finish_response,
    text_response,
)

from portal.modules.orchestration.ledger import ResumeMismatchError  # noqa: E402
from portal.modules.orchestration.planner import validate_planned_plan  # noqa: E402
from portal.modules.orchestration.service import (  # noqa: E402
    ArmService,
    StubNoticeSink,
    load_arm_config,
)
from portal.modules.orchestration.worker import Engine  # noqa: E402
from portal.platform.mcp_host.workspace import get_generated_dir  # noqa: E402
from scripts import host_quiet  # noqa: E402

_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}

# WFE coordination. tests/wfe/run_arm.py writes the PID file; the unattended
# sweep runs `python -m tests.wfe.campaign` directly, so the process table is
# the only reliable signal for that mode.
WFE_PID_FILE = Path("/tmp/portal5-memory-safety-test-pids")
WFE_PROCESS_PATTERNS = (
    "tests.wfe.campaign",
    "tests/wfe/run_arm.py",
    "wfe_sweep_unattended.sh",
)

# The live check must be satisfiable from the prompt, so the checked token is stated in the goal.
LIVE_TOKEN = "arm-live-ok"


class ScenarioSkippedError(RuntimeError):
    """The scenario cannot run in this mode and must not be reported as PASS."""


class DryRunNoticeSink(StubNoticeSink):
    """Captures Telegram-like notices for dry-run verification."""

    def __init__(self) -> None:
        super().__init__()
        self.approval_requests: list[tuple[str, str, dict[str, Any], str, str]] = []

    def approval(
        self,
        task_id: str,
        bite_id: str,
        bite_definition: dict[str, Any],
        reason: str,
        run_id: str,
    ) -> bool | None:
        self.approval_requests.append((task_id, bite_id, bite_definition, reason, run_id))
        return None  # "wait" - we simulate deny by not returning True


def _head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _pid_file_reason(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return f"PID file {path} is unreadable ({type(exc).__name__}); failing closed"
    for line in lines:
        value = line.strip()
        if not value:
            continue
        try:
            pid = int(value)
        except ValueError:
            return f"unparseable PID line {value!r} in {path}; failing closed"
        if pid <= 0:
            return f"invalid PID {pid} in {path}; failing closed"
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        except OSError:
            return f"PID {pid} in {path} cannot be checked; failing closed"
        return f"PID {pid} in {path} is live"
    return None


def _wfe_processes() -> list[str]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"process table unavailable ({type(exc).__name__}); failing closed"]
    if result.returncode:
        return ["ps failed; failing closed"]
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if any(pattern in line for pattern in WFE_PROCESS_PATTERNS)
    ]


def _wfe_active() -> str | None:
    reason = _pid_file_reason(WFE_PID_FILE)
    if reason:
        return reason
    processes = _wfe_processes()
    if processes:
        return f"WFE process running: {processes[0]}"
    return None


def _write_arm_config(
    path: Path, *, calibration_overrides: dict[str, Any] | None = None
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load((ROOT / "config" / "orchestration_arm.yaml").read_text())
    config["calibration"]["minimum_pass_probability"] = 0.01
    config["calibration"]["rates_by_discipline"] = {
        name: {
            "fast": {"pass_probability": 1.0, "mean_seconds": 1},
            "deep": {"pass_probability": 1.0, "mean_seconds": 1},
        }
        for name in ("offline-rig", "test_fixing")
    }
    config["disciplines"]["offline-rig"] = {
        "tool_allowlist": ["file_read", "file_write", "pytest_run"],
        "read_tools": ["file_read"],
        "action_tools": ["file_write", "pytest_run"],
    }
    if calibration_overrides:
        config["calibration"].update(calibration_overrides)
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config


def _bite(
    bite_id: str,
    *,
    text: bool = False,
    tokens: int = 256,
    discipline: str = "offline-rig",
    risk: str = "low",
    tools: list[str] | None = None,
    model: str = "fast",
    depends_on: list[str] | None = None,
    stage: str = "work",
) -> dict[str, Any]:
    output = (
        {"path": f"bites/{bite_id}/output.txt", "file_type": "text"}
        if text
        else {
            "path": f"bites/{bite_id}/output.json",
            "schema": _SCHEMA,
        }
    )
    accept = (
        [{"type": "contains", "value": "right"}]
        if text
        else [{"type": "equals", "path": "$.answer", "value": "right"}]
    )
    return {
        "bite_id": bite_id,
        "goal": "produce the expected value",
        "discipline": discipline,
        "inputs": [],
        **({"write_paths": ["artifact.txt"]} if "file_write" in (tools or []) else {}),
        "depends_on": depends_on or [],
        "tools": tools or [],
        "output": output,
        "accept": accept,
        "risk": risk,
        "stage": stage,
        "budget": {"turns": 2, "minutes": 1, "output_tokens": tokens, "context_tokens": 512},
        "model": model,
        "procedure": "Follow the configured procedure.",
    }


def _live_bite() -> dict[str, Any]:
    """A live bite a real model can satisfy: the goal states the checked token."""
    bite = _bite("b1", text=True, discipline="test_fixing", tokens=1024)
    bite["goal"] = f"Call finish once with output text containing {LIVE_TOKEN}."
    bite["procedure"] = f"Reply with {LIVE_TOKEN}; surrounding text is fine."
    bite["accept"] = [{"type": "contains", "value": LIVE_TOKEN}]
    return bite


def _run_task(
    root: Path,
    task_id: str,
    responses: list[tuple[str, Any]],
    bites: list[dict[str, Any]],
    notices: Any = None,
    calibration_overrides: dict[str, Any] | None = None,
    *,
    close: bool = True,
) -> tuple[dict[str, Any], FakePipeline]:
    pipeline = FakePipeline()
    for seat, response in responses:
        pipeline.add(seat, response)
    config = root / "config" / "orchestration_arm.yaml"
    _write_arm_config(config, calibration_overrides=calibration_overrides)
    engines = {
        "fast": Engine("auto-daily::fast", "fast-digest", pipeline.url, "", "omlx", "fake-fast"),
        "deep": Engine("auto-daily::deep", "deep-digest", pipeline.url, "", "omlx", "fake-deep"),
    }
    service = ArmService(
        root, engines, build_sha="offline-head", residency_config=config, notices=notices
    )
    task = service.submit(
        {"task_id": task_id, "goal": "Offline rig scenario", "bites": bites}, root
    )
    receipt = json.loads((task / "receipt.json").read_text(encoding="utf-8"))
    if close:
        pipeline.close()
    return receipt, pipeline


def _run_live_task(
    root: Path,
    task_id: str,
    bites: list[dict[str, Any]],
    pipeline_url: str,
    api_key: str,
    fast_digest: str,
    deep_digest: str,
    notices: Any = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    config = config_path or ROOT / "config" / "orchestration_arm.yaml"
    arm_config = load_arm_config(config)
    load_plan = arm_config.get("load_plan_models", {})
    engines = {}
    for seat in ("fast", "deep"):
        load_identity = load_plan.get(seat, {}) if isinstance(load_plan, dict) else {}
        engines[seat] = Engine(
            f"auto-daily::{seat}",
            fast_digest if seat == "fast" else deep_digest,
            pipeline_url,
            api_key,
            str(load_identity.get("engine", "omlx")),
            str(load_identity.get("model", "")),
        )
    service = ArmService(root, engines, residency_config=config, notices=notices)
    task = service.submit(
        {"task_id": task_id, "goal": "Live acceptance scenario", "bites": bites},
        root,
        unattended=False,
    )
    return json.loads((task / "receipt.json").read_text(encoding="utf-8"))


def _failures(receipt: dict[str, Any], bite_id: str = "b1") -> list[str]:
    for result in receipt["results"]:
        if result.get("bite_id") == bite_id and result.get("failure"):
            return list(result["failure"].get("failures", []))
    return []


def _bite_failure(receipt: dict[str, Any], bite_id: str = "b1") -> str:
    """Name the recorded cause so a live assertion failure is actionable."""
    for result in receipt.get("results", []):
        if result.get("bite_id") != bite_id:
            continue
        failure = result.get("failure") or {}
        detail = failure.get("failures") or failure.get("reason") or "no recorded failure"
        return f"{result.get('status')} after {result.get('attempts')} attempt(s): {detail}"
    return f"no result recorded for bite {bite_id}"


# --- Phase 1 (Gate B) Scenarios ---


def scenario_happy_path(root: Path, task_id: str, live: bool, pipeline: Any, **kw) -> str:
    if live:
        receipt = _run_live_task(root, task_id, [_live_bite()], **kw)
        result = next((row for row in receipt.get("results", []) if row.get("bite_id") == "b1"), {})
        if receipt["status"] != "PASS" or result.get("attempts") != 1:
            raise AssertionError(_bite_failure(receipt, "b1"))
        return "one live Fast request returned the token its goal asked for"
    receipt, pipeline = _run_task(
        root, task_id, [("fast", finish_response({"answer": "right"}))], [_bite("b1")]
    )
    assert receipt["status"] == "PASS" and pipeline.requests[0]["model"] == "auto-daily::fast"
    return "one auto-daily::fast request passed through the fake Pipeline port"


def scenario_red_flag_retry(root: Path, task_id: str, live: bool, pipeline: Any, **kw) -> str:
    if live:
        raise ScenarioSkippedError("requires controllable responses")
    receipt, _ = _run_task(
        root,
        task_id,
        [
            ("fast", finish_response("I cannot help with this request.")),
            ("fast", finish_response("right")),
        ],
        [_bite("b1", text=True)],
    )
    assert receipt["status"] == "PASS" and receipt["results"][0]["attempts"] == 2
    assert "refusal" in _attempt_failures(root, task_id, "b1", 1)
    return "refusal red flag discarded; second Fast attempt passed"


def _attempt_failures(root: Path, task_id: str, bite_id: str, attempt: int) -> list[str]:
    path = root / task_id / "bites" / bite_id / "attempts" / f"{attempt:02d}" / "checks.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    return list(record.get("failures", []))


def scenario_budget_exhaustion(root: Path, task_id: str, live: bool, pipeline: Any, **kw) -> str:
    if live:
        raise ScenarioSkippedError("requires controllable responses")
    responses = [
        (seat, finish_response({"answer": "right"}, tokens=50))
        for seat in ("fast", "fast", "fast", "deep")
    ]
    receipt, _ = _run_task(root, task_id, responses, [_bite("b1", tokens=8)])
    assert receipt["status"] == "BLOCKED"
    assert "output_token_cap" in _failures(receipt)
    return "output-token cap blocked the bite after the failure ladder"


def scenario_wandering_bite(root: Path, task_id: str, live: bool, pipeline: Any, **kw) -> str:
    if live:
        raise ScenarioSkippedError("requires controllable responses")
    responses = [(seat, text_response("working")) for seat in ("fast", "fast", "fast", "deep")]
    receipt, _ = _run_task(root, task_id, responses, [_bite("b1")])
    assert receipt["status"] == "BLOCKED"
    assert "missing_finish" in _failures(receipt)
    return "missing finish call blocked the bite"


def scenario_pipeline_failure(root: Path, task_id: str, live: bool, pipeline: Any, **kw) -> str:
    if live:
        raise ScenarioSkippedError("requires controllable responses")
    receipt, pipeline = _run_task(
        root,
        task_id,
        [("fast", "HTTP_500"), ("fast", finish_response({"answer": "right"}))],
        [_bite("b1")],
    )
    assert receipt["status"] == "PASS" and len(pipeline.requests) == 2
    assert any("HTTPStatusError" in item for item in _attempt_failures(root, task_id, "b1", 1))
    return "HTTP 500 mid-bite retried through the Pipeline and passed"


def scenario_sigterm_resume(root: Path, task_id: str, live: bool, pipeline: Any, **kw) -> str:
    if live:
        raise ScenarioSkippedError("requires controllable SIGTERM injection")
    pipeline = FakePipeline()
    pipeline.add("fast", SignalResponse(finish_response({"answer": "right"})))
    pipeline.add("fast", finish_response({"answer": "right"}))
    config = root / "config" / "orchestration_arm.yaml"
    _write_arm_config(config)
    engines = {
        "fast": Engine("auto-daily::fast", "fast-digest", pipeline.url, "", "omlx", "fake-fast"),
        "deep": Engine("auto-daily::deep", "deep-digest", pipeline.url, "", "omlx", "fake-deep"),
    }
    runner = ArmService(root, engines, build_sha="offline-head", residency_config=config)
    previous = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        try:
            runner.submit({"task_id": task_id, "goal": "resume", "bites": [_bite("b1")]}, root)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("fake server did not interrupt the first request")
    finally:
        signal.signal(signal.SIGTERM, previous)
    runner.resume(task_id)
    receipt = json.loads((root / task_id / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    pipeline.close()
    return "SIGTERM left a running bite; resume requeued it and passed"


def scenario_identity_mismatch(root: Path, task_id: str, live: bool, pipeline: Any, **kw) -> str:
    if live:
        raise ScenarioSkippedError("requires reproducible build/digest mismatch")
    pipeline = FakePipeline()
    pipeline.add("fast", finish_response({"answer": "right"}))
    config = root / "config" / "orchestration_arm.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    _write_arm_config(config)
    engines = {
        "fast": Engine("auto-daily::fast", "fast-digest", pipeline.url, "", "omlx", "fake-fast"),
        "deep": Engine("auto-daily::deep", "deep-digest", pipeline.url, "", "omlx", "fake-deep"),
    }
    root.mkdir(parents=True, exist_ok=True)
    ArmService(root, engines, build_sha="head-a", residency_config=config).submit(
        {"task_id": task_id, "goal": "mismatch", "bites": [_bite("b1")]}, root
    )
    try:
        ArmService(root, engines, build_sha="head-b", residency_config=config).resume(task_id)
    except ResumeMismatchError as exc:
        assert "build SHA" in str(exc)
    else:
        raise AssertionError("changed build SHA was accepted")
    changed = {
        "fast": Engine("auto-daily::fast", "other-digest", pipeline.url, "", "omlx", "fake-fast"),
        "deep": Engine("auto-daily::deep", "deep-digest", pipeline.url, "", "omlx", "fake-deep"),
    }
    try:
        ArmService(root, changed, build_sha="head-a", residency_config=config).resume(task_id)
    except ResumeMismatchError as exc:
        assert "model digest" in str(exc)
    else:
        raise AssertionError("changed model digest was accepted")
    pipeline.close()
    return "resume refused the changed build SHA and the changed model digest"


def scenario_blocked_branch_independent_pass(
    root: Path, task_id: str, live: bool, pipeline: Any, **kw
) -> str:
    if live:
        raise ScenarioSkippedError("requires controllable responses")
    responses = [
        (seat, finish_response({"answer": "wrong"})) for seat in ("fast", "fast", "fast", "deep")
    ]
    responses.append(("fast", finish_response({"answer": "right"})))
    receipt, _ = _run_task(root, task_id, responses, [_bite("bad"), _bite("independent")])
    statuses = {result["bite_id"]: result["status"] for result in receipt["results"]}
    assert statuses == {"bad": "BLOCKED", "independent": "PASS"}
    return "failed bite blocked while independent branch passed"


# --- Phase 2 (Gate C) Scenarios ---


def _valid_planned_plan() -> dict[str, Any]:
    def _bite(bite_id: str, stage: str, tools: list[str], deps: list[str]) -> dict[str, Any]:
        return {
            "bite_id": bite_id,
            "goal": f"Complete {stage} for the task.",
            "discipline": "test_fixing",
            "inputs": [],
            **({"write_paths": ["artifact.txt"]} if "file_write" in tools else {}),
            "depends_on": deps,
            "tools": tools,
            "output": {"path": f"bites/{bite_id}.txt", "file_type": "text"},
            "accept": [{"type": "contains", "value": "done"}],
            "risk": "low",
            "stage": stage,
            "budget": {"turns": 2, "minutes": 2, "output_tokens": 128, "context_tokens": 512},
            "model": "fast",
            "procedure": "Follow the configured test-fixing procedure.",
        }

    final = _bite("final", "final_review", [], ["assembly"])
    final["accept"] = []
    final["review"] = "deep"
    final["review_reason"] = "Check the assembled fix is complete."
    final["model"] = "deep"
    return {
        "task_id": "planner-fixture",
        "goal": "Repair one failing unit test.",
        "bites": [
            _bite("inspect", "work", ["file_read"], []),
            _bite("assembly", "assembly", ["file_write", "pytest_run"], ["inspect"]),
            final,
        ],
    }


def scenario_planner_missing_check(
    root: Path, task_id: str, live: bool, pipeline: Any, **kw
) -> str:
    config = yaml.safe_load((ROOT / "config" / "orchestration_arm.yaml").read_text())
    raw = _valid_planned_plan()
    raw["bites"][0]["accept"] = []
    try:
        validate_planned_plan(raw, config, "test_fixing")
    except ValueError as exc:
        assert "deterministic check or review" in str(exc)
        return "validator rejected missing check"
    raise AssertionError("validator accepted missing check")


def scenario_planner_context_overflow(
    root: Path, task_id: str, live: bool, pipeline: Any, **kw
) -> str:
    config = yaml.safe_load((ROOT / "config" / "orchestration_arm.yaml").read_text())
    raw = _valid_planned_plan()
    raw["bites"][0]["budget"]["context_tokens"] = 16385
    try:
        validate_planned_plan(raw, config, "test_fixing")
    except ValueError as exc:
        assert "exceeds Fast context budget" in str(exc)
        return "validator rejected context overflow"
    raise AssertionError("validator accepted context overflow")


def scenario_planner_mixed_read_and_action(
    root: Path, task_id: str, live: bool, pipeline: Any, **kw
) -> str:
    config = yaml.safe_load((ROOT / "config" / "orchestration_arm.yaml").read_text())
    raw = _valid_planned_plan()
    raw["bites"][0]["tools"] = ["file_read", "file_write"]
    try:
        validate_planned_plan(raw, config, "test_fixing")
    except ValueError as exc:
        assert "reading and acting" in str(exc)
        return "validator rejected mixed read and action"
    raise AssertionError("validator accepted mixed read and action")


def scenario_planner_missing_assembly_and_review(
    root: Path, task_id: str, live: bool, pipeline: Any, **kw
) -> str:
    config = yaml.safe_load((ROOT / "config" / "orchestration_arm.yaml").read_text())
    raw = _valid_planned_plan()
    raw["bites"][-1]["stage"] = "work"
    try:
        validate_planned_plan(raw, config, "test_fixing")
    except ValueError as exc:
        assert "assembly and final_review" in str(exc)
        return "validator rejected missing assembly and final_review"
    raise AssertionError("validator accepted missing assembly and final_review")


class _FakeDenyNotices(DryRunNoticeSink):
    def approval(
        self,
        task_id: str,
        bite_id: str,
        bite_definition: dict[str, Any],
        reason: str,
        run_id: str,
    ) -> bool | None:
        self.approval_requests.append((task_id, bite_id, bite_definition, reason, run_id))
        return False


class _FakeApproveNotices(DryRunNoticeSink):
    def approval(
        self,
        task_id: str,
        bite_id: str,
        bite_definition: dict[str, Any],
        reason: str,
        run_id: str,
    ) -> bool | None:
        self.approval_requests.append((task_id, bite_id, bite_definition, reason, run_id))
        return True


def scenario_deep_vote_split(root: Path, task_id: str, live: bool, pipeline: Any, **kw) -> str:
    if live:
        raise ScenarioSkippedError("requires controllable Deep responses")
    responses = [("fast", finish_response({"answer": "right"}))]
    responses.extend(
        [
            ("deep", text_response('{"decision":"approve","reason":"complete"}')),
            ("deep", text_response('{"decision":"reject","reason":"minor gap"}')),
            ("deep", text_response('{"decision":"approve","reason":"checks hold"}')),
        ]
    )
    receipt, _ = _run_task(root, task_id, responses, [_bite("b1", risk="high")])
    review = json.loads(
        (root / task_id / "bites/b1/attempts/01/checks.json").read_text(encoding="utf-8")
    )["deep_review"]
    assert receipt["status"] == "PASS" and review["approvals"] == 2 and len(review["votes"]) == 3
    return "configured 2-of-3 Deep vote passed with one dissent"


def scenario_telegram_deny(root: Path, task_id: str, live: bool, pipeline: Any, **kw) -> str:
    if live:
        raise ScenarioSkippedError("requires Telegram integration")
    notices = _FakeDenyNotices()
    receipt, pipeline = _run_task(
        root,
        task_id,
        [],
        [_bite("write", discipline="test_fixing", risk="high", tools=["file_write"])],
        notices=notices,
    )
    assert receipt["status"] == "BLOCKED" and len(notices.approval_requests) == 1
    assert not pipeline.requests
    assert "denied" in str(notices.notices[0]["failure"])
    return "fake Telegram deny blocked the write before any Pipeline bite ran"


def scenario_telegram_approve(root: Path, task_id: str, live: bool, pipeline: Any, **kw) -> str:
    if live:
        raise ScenarioSkippedError("requires Telegram integration")
    notices = _FakeApproveNotices()
    responses = [("fast", finish_response({"answer": "right"}))]
    responses.extend(
        ("deep", text_response('{"decision":"approve","reason":"complete"}')) for _ in range(3)
    )
    receipt, pipeline = _run_task(
        root,
        task_id,
        responses,
        [_bite("write", discipline="test_fixing", risk="high", tools=["file_write"])],
        notices=notices,
    )
    assert receipt["status"] == "PASS" and len(notices.approval_requests) == 1
    assert len(pipeline.requests) == 4
    return "fake Telegram approval opened the gate before the high-risk write"


def scenario_calibration_pause(root: Path, task_id: str, live: bool, pipeline: Any, **kw) -> str:
    if live:
        raise ScenarioSkippedError("requires Gate C rates")
    receipt, pipeline = _run_task(
        root,
        task_id,
        [("fast", finish_response({"answer": "right"}))],
        [_bite("b1"), _bite("b2"), _bite("b3")],
        calibration_overrides={
            "after_bites": 1,
            "minimum_pass_probability": 0.9,
            "rates_by_discipline": {
                "offline-rig": {
                    "fast": {"pass_probability": 0.5, "mean_seconds": 10},
                    "deep": {"pass_probability": 0.5, "mean_seconds": 20},
                }
            },
        },
        close=False,
    )
    assert receipt["status"] == "PAUSED_FOR_REPLAN"
    assert receipt["calibration"][0]["projected_pass_probability"] == 0.25
    assert len(pipeline.requests) == 1
    engines = {
        "fast": Engine("auto-daily::fast", "fast-digest", pipeline.url, "", "omlx", "fake-fast"),
        "deep": Engine("auto-daily::deep", "deep-digest", pipeline.url, "", "omlx", "fake-deep"),
    }
    runner = ArmService(
        root,
        engines,
        build_sha="offline-head",
        residency_config=root / "config" / "orchestration_arm.yaml",
    )
    try:
        runner.resume(task_id, unattended=False)
    except ValueError as exc:
        assert "replacement plan" in str(exc)
    else:
        raise AssertionError("calibration pause resumed without a replacement plan")
    finally:
        pipeline.close()
    return "Gate C paused after one bite when remaining projected odds fell below threshold"


SCENARIOS: dict[str, dict[str, Any]] = {
    # Phase 1 (Gate B)
    "happy_path": {"phase": 1, "fn": scenario_happy_path, "required": True},
    "red_flag_retry": {"phase": 1, "fn": scenario_red_flag_retry, "required": True},
    "budget_exhaustion": {"phase": 1, "fn": scenario_budget_exhaustion, "required": True},
    "wandering_bite": {"phase": 1, "fn": scenario_wandering_bite, "required": True},
    "pipeline_failure": {"phase": 1, "fn": scenario_pipeline_failure, "required": True},
    "sigterm_resume": {"phase": 1, "fn": scenario_sigterm_resume, "required": True},
    "identity_mismatch": {"phase": 1, "fn": scenario_identity_mismatch, "required": True},
    "blocked_branch_independent_pass": {
        "phase": 1,
        "fn": scenario_blocked_branch_independent_pass,
        "required": True,
    },
    # Phase 2 (Gate C)
    "planner_missing_check": {"phase": 2, "fn": scenario_planner_missing_check, "required": True},
    "planner_context_overflow": {
        "phase": 2,
        "fn": scenario_planner_context_overflow,
        "required": True,
    },
    "planner_mixed_read_and_action": {
        "phase": 2,
        "fn": scenario_planner_mixed_read_and_action,
        "required": True,
    },
    "planner_missing_assembly_and_review": {
        "phase": 2,
        "fn": scenario_planner_missing_assembly_and_review,
        "required": True,
    },
    "deep_vote_split": {"phase": 2, "fn": scenario_deep_vote_split, "required": True},
    "telegram_deny": {"phase": 2, "fn": scenario_telegram_deny, "required": True},
    "telegram_approve": {"phase": 2, "fn": scenario_telegram_approve, "required": True},
    "calibration_pause": {"phase": 2, "fn": scenario_calibration_pause, "required": True},
}


def run_scenario(
    name: str,
    workdir: Path,
    live: bool,
    pipeline_url: str,
    api_key: str,
    fast_digest: str,
    deep_digest: str,
) -> dict[str, Any]:
    """Run one scenario and return PASS, FAIL or SKIP."""
    scenario = SCENARIOS[name]
    required = bool(scenario.get("required", True))
    task_dir = workdir / "tasks" / name
    task_dir.mkdir(parents=True, exist_ok=True)
    # A per-run task id keeps a repeated run from colliding with the previous run's task.
    task_id = f"{name}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
    try:
        evidence = scenario["fn"](
            task_dir,
            task_id,
            live=live,
            pipeline=None,
            pipeline_url=pipeline_url,
            api_key=api_key,
            fast_digest=fast_digest,
            deep_digest=deep_digest,
        )
        status = "PASS"
    except ScenarioSkippedError as exc:
        status, evidence = "SKIP", f"skipped in live mode ({exc})"
    except Exception as exc:
        status, evidence = "FAIL", f"{type(exc).__name__}: {exc}"
    return {
        "scenario": name,
        "status": status,
        "evidence": evidence,
        "phase": str(scenario["phase"]),
        "required": required,
    }


def _summary(results: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(results),
        "passed": sum(result["status"] == "PASS" for result in results),
        "failed": sum(result["status"] == "FAIL" for result in results),
        "skipped": sum(result["status"] == "SKIP" for result in results),
        "required_skipped": sum(
            result["status"] == "SKIP" and result.get("required") for result in results
        ),
    }


def _receipt(
    workdir: Path,
    results: list[dict[str, Any]],
    *,
    mode: str,
    pipeline_url: str | None = None,
    fast_digest: str = "",
    deep_digest: str = "",
    wfe: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "head": _head_sha(),
        "utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": mode,
        "gate_evidence": False,
        "scope": "smoke/wiring harness; not Gate B/C exit evidence",
        "pipeline_url": pipeline_url,
        "model_digests": {"fast": fast_digest, "deep": deep_digest},
        "wfe": wfe,
        "workdir": str(workdir.resolve()),
        "summary": _summary(results),
        "results": results,
        **extra,
    }


def run_dry_run(workdir: Path, phases: list[int] | None = None) -> dict[str, Any]:
    """Run the selected scenarios against the fake Pipeline rig."""
    results = []
    for name, meta in SCENARIOS.items():
        if phases and meta["phase"] not in phases:
            continue
        print(f"  {name}...", end=" ", flush=True)
        result = run_scenario(
            name, workdir, live=False, pipeline_url="", api_key="", fast_digest="", deep_digest=""
        )
        results.append(result)
        print(result["status"])
    return _receipt(workdir, results, mode="dry-run", wfe="not checked (dry-run)")


def run_live(
    workdir: Path,
    pipeline_url: str,
    api_key: str,
    fast_digest: str,
    deep_digest: str,
    phases: list[int] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Run scenarios against a live Pipeline after the shared host preflight."""
    print("Checking that the host is quiet...", flush=True)
    host_context = host_quiet.begin_run(pipeline_url, api_key, force=force)
    if not host_context["allowed"]:
        reason = host_quiet.refusal(host_context)
        host_quiet.finish_run(host_context, pipeline_url, api_key)
        print(f"ERROR: {reason}", file=sys.stderr)
        return _receipt(
            workdir,
            [],
            mode="live",
            pipeline_url=pipeline_url,
            wfe=reason,
            blocked=reason,
            host_quiet=host_context,
        )
    if host_context["override_reason"]:
        print(f"HOST-QUIET OVERRIDE: {host_context['override_reason']}", file=sys.stderr)
    results: list[dict[str, Any]] = []
    aborted = None
    interrupted = False
    try:
        for name, meta in SCENARIOS.items():
            if phases and meta["phase"] not in phases:
                continue
            reason = None if force else _wfe_active()
            if reason:
                aborted = f"WFE became active before {name}: {reason}"
                print(f"\nABORT: {aborted}", file=sys.stderr, flush=True)
                break
            print(f"  {name}...", end=" ", flush=True)
            result = run_scenario(
                name,
                workdir,
                live=True,
                pipeline_url=pipeline_url,
                api_key=api_key,
                fast_digest=fast_digest,
                deep_digest=deep_digest,
            )
            results.append(result)
            print(result["status"])
    except KeyboardInterrupt:
        interrupted = True
        print("\nInterrupted; writing a partial receipt", file=sys.stderr, flush=True)
    host_quiet.finish_run(host_context, pipeline_url, api_key)
    return _receipt(
        workdir,
        results,
        mode="live",
        pipeline_url=pipeline_url,
        fast_digest=fast_digest,
        deep_digest=deep_digest,
        wfe="clear" if aborted is None else aborted,
        aborted=aborted,
        interrupted=interrupted,
        host_quiet=host_context,
    )


def _md_cell(value: Any) -> str:
    return (
        str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    )


def write_receipts(workdir: Path, receipt: dict[str, Any]) -> tuple[Path, Path]:
    """Write JSON and Markdown receipts."""
    json_path = workdir / "acceptance_receipt.json"
    md_path = workdir / "acceptance_receipt.md"

    json_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    summary = receipt["summary"]
    lines = [
        "# Orchestration Acceptance Receipt",
        "",
        f"**HEAD**: {receipt['head']}",
        f"**UTC**: {receipt['utc']}",
        f"**Mode**: {receipt['mode']}",
        f"**Gate evidence**: {'yes' if receipt.get('gate_evidence') else 'no'} — {receipt['scope']}",
        f"**Workdir**: {receipt['workdir']}",
        f"**Summary**: {summary['passed']} passed, {summary['failed']} failed, "
        f"{summary['skipped']} skipped ({summary['required_skipped']} required)",
        "",
        "| Scenario | Phase | Status | Required | Evidence |",
        "|---|---|---|---|---|",
    ]
    for r in receipt["results"]:
        lines.append(
            f"| {_md_cell(r['scenario'])} | {r['phase']} | {r['status']} | "
            f"{'yes' if r.get('required') else 'no'} | {_md_cell(r['evidence'])} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return json_path, md_path


def _exit_code(receipt: dict[str, Any]) -> int:
    if receipt.get("blocked"):
        return 3
    if receipt.get("interrupted"):
        return 130
    if receipt.get("aborted"):
        return 1
    results = receipt.get("results", [])
    if any(result["status"] == "FAIL" for result in results):
        return 1
    if any(result["status"] == "SKIP" and result.get("required") for result in results):
        return 1
    return 0


def _default_workdir() -> Path:
    return get_generated_dir("tasks") / "arm-acceptance"


def _interrupt(_signum: int, _frame: Any) -> None:
    raise KeyboardInterrupt


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline-url", default="http://127.0.0.1:9099", help="Pipeline base URL")
    parser.add_argument(
        "--api-key", default=os.environ.get("PIPELINE_API_KEY", ""), help="Pipeline API key"
    )
    parser.add_argument(
        "--fast-digest",
        default=os.environ.get("PORTAL_ARM_FAST_DIGEST", ""),
        help="Fast seat model digest",
    )
    parser.add_argument(
        "--deep-digest",
        default=os.environ.get("PORTAL_ARM_DEEP_DIGEST", ""),
        help="Deep seat model digest",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=None,
        help="Working directory (default: <tasks dir>/arm-acceptance)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Run against fake Pipeline rig (offline)"
    )
    parser.add_argument("--force", action="store_true", help="override host-quiet blockers")
    parser.add_argument(
        "--phase", type=int, action="append", choices=[1, 2], help="Run only specific phase(s)"
    )
    return parser.parse_args()


def _live_args_valid(args: argparse.Namespace) -> bool:
    if not args.api_key:
        print("ERROR: PIPELINE_API_KEY required for live run", file=sys.stderr)
        return False
    if not args.fast_digest or not args.deep_digest:
        print(
            "ERROR: PORTAL_ARM_FAST_DIGEST and PORTAL_ARM_DEEP_DIGEST required for live run",
            file=sys.stderr,
        )
        return False
    return True


def _run(args: argparse.Namespace, workdir: Path) -> dict[str, Any]:
    previous = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, _interrupt)
    try:
        if args.dry_run:
            return run_dry_run(workdir, phases=args.phase)
        return run_live(
            workdir,
            args.pipeline_url,
            args.api_key,
            args.fast_digest,
            args.deep_digest,
            phases=args.phase,
            force=args.force,
        )
    finally:
        signal.signal(signal.SIGTERM, previous)


def _print_outcome(receipt: dict[str, Any]) -> None:
    summary = receipt["summary"]
    print(
        f"\nSummary: {summary['passed']} passed, {summary['failed']} failed, "
        f"{summary['skipped']} skipped ({summary['required_skipped']} required)"
    )
    for key, label in (
        ("blocked", "BLOCKED"),
        ("aborted", "ABORTED"),
        ("interrupted", "INTERRUPTED: partial receipt written"),
    ):
        if receipt.get(key):
            detail = f": {receipt[key]}" if isinstance(receipt[key], str) else ""
            print(f"\n{label}{detail}", file=sys.stderr)
    for result in receipt["results"]:
        if result["status"] == "FAIL":
            print(f"  FAIL {result['scenario']}: {result['evidence']}", file=sys.stderr)
        if result["status"] == "SKIP" and result.get("required"):
            print(f"  SKIP {result['scenario']}: {result['evidence']}", file=sys.stderr)


def main() -> int:
    args = _parse_args()
    workdir = args.workdir or _default_workdir()
    workdir.mkdir(parents=True, exist_ok=True)
    print(f"Work directory: {workdir}")
    print(f"Mode: {'dry-run (fake rig)' if args.dry_run else 'live'}")
    if not args.dry_run:
        print(f"Pipeline: {args.pipeline_url}")
        if not _live_args_valid(args):
            return 2
    try:
        receipt = _run(args, workdir)
    except KeyboardInterrupt:
        print("\nInterrupted before a receipt was written", file=sys.stderr)
        return 130
    json_path, md_path = write_receipts(workdir, receipt)
    print("\nReceipts written:")
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")
    _print_outcome(receipt)
    return _exit_code(receipt)


if __name__ == "__main__":
    raise SystemExit(main())
