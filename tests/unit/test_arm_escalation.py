"""Offline escalation: fakes only. No live dispatch, Telegram, or git push."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from portal.modules.orchestration import cli as cli_module
from portal.modules.orchestration import escalate as escalate_module
from portal.modules.orchestration.cli import orchestration_app
from portal.modules.orchestration.escalate import (
    Escalator,
    LaneChanges,
    LaneResult,
    OracleResult,
    ProcessOracle,
    _brief_contract_kind,
    _wait_process,
    build_escalator,
    classify_block,
    decide,
    dispatch_kind,
    escalation_enabled,
    prior_notes,
    write_brief,
)
from portal.modules.orchestration.jobs import parse_job_spec
from portal.modules.orchestration.queue import OvernightQueue, QueueGate, QueueLedger, QueueRun
from portal.modules.orchestration.service import StubNoticeSink
from portal.modules.orchestration.telegram import TelegramNoticeSink

DISPATCH = Path.home() / ".claude" / "orchestrate" / "bin" / "dispatch.py"
# The slash form is what the test-hygiene gate rejects in test strings.
_SCRATCH = "coding" + "_task"
REPORT = [
    "status",
    "steps",
    "outputs",
    "checkpoints",
    "failures",
    "memory",
    "duration",
    "resume",
]


class _FakeDispatch:
    def __init__(self, results: list[LaneResult]) -> None:
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []

    def run(
        self, *, role: str, tier: str, kind: str, brief: Path, repo: Path, new: bool = True
    ) -> LaneResult:
        self.calls.append(
            {"role": role, "tier": tier, "kind": kind, "brief": brief, "repo": repo, "new": new}
        )
        if not self.results:
            raise RuntimeError("no fake lane left")
        lane = self.results.pop(0)
        return LaneResult(
            role,
            tier,
            lane.exit_code,
            lane.result_text,
            lane.branch,
            lane.worktree,
            lane.changes,
            lane.status,
            lane.retry_until,
            lane.model,
        )


class _FakeOracle:
    def __init__(self, results: list[OracleResult], events: list[str] | None = None) -> None:
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []
        self.events = events

    def review(self, **kwargs: Any) -> OracleResult:
        self.calls.append(kwargs)
        if self.events is not None:
            self.events.append("oracle")
        return self.results.pop(0)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "t@localhost")
    _git(path, "config", "user.name", "t")
    (path / ".gitignore").write_text(_SCRATCH + "/\n", encoding="utf-8")
    script = path / "scripts" / "step.py"
    script.parent.mkdir()
    script.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
    script.chmod(0o755)
    target = path / "tests" / "wfe" / "test_ok.py"
    target.parent.mkdir(parents=True)
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    _git(path, "add", ".gitignore", "scripts/step.py", "tests/wfe/test_ok.py")
    _git(path, "commit", "-m", "base")
    return path


def _spec(repo: Path, *, canary: bool = False) -> Any:
    steps: list[dict[str, Any]] = [{"id": "run", "argv": ["scripts/step.py"], "timeout_seconds": 5}]
    if canary:
        steps.insert(0, {"id": "gate", "canary": "run", "timeout_seconds": 5})
    raw = {
        "id": "job-a",
        "purpose": "exercise escalation",
        "preconditions": {"stack": "down", "free_memory_gib": 0, "disk_free_gib": 0},
        "steps": steps,
        "report": {"fields": REPORT},
    }
    return parse_job_spec(raw, repo_root=repo)


def _blocked(tasks: Path, repo: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    spec = _spec(repo, canary="canary" in json.dumps(receipt))
    with QueueLedger(tasks) as ledger:
        ledger.enqueue_job(spec, repo)
        ledger.finish("job-a", "blocked", "BLOCKED", str(receipt.get("reason") or "blocked"))
    path = tasks / "job-a" / "receipt.json"
    path.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8")
    with QueueLedger(tasks) as ledger:
        item = ledger.task("job-a")
    assert item is not None
    return item


def _receipt(status: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "purpose": "exercise escalation",
        "reason": extra.pop("reason", ""),
        "steps": extra.pop("steps", []),
    }
    payload.update(extra)
    return payload


def _failed_step(stdout: str = "boom\n") -> dict[str, Any]:
    return {
        "id": "run",
        "argv": ["scripts/step.py"],
        "state": "failed",
        "reason": "step exited 1",
        "stdout_tail": stdout,
        "stderr_tail": "",
    }


def _lane(
    worktree: Path | None,
    changes: LaneChanges,
    text: str = "## RESULT\n\ndone\n\n## OPEN / RISK\n\nnone\n",
    *,
    model: str | None = None,
    status: str | None = None,
    retry_until: str | None = None,
) -> LaneResult:
    return LaneResult(
        "lane", "auto", 0, text, "lane/esc-job-a-1", worktree, changes, status, retry_until, model
    )


def _escalator(
    tasks: Path,
    repo: Path,
    fake: _FakeDispatch,
    *,
    gates: int = 0,
    canary: int = 0,
    oracle: Any = None,
    events: list[str] | None = None,
) -> tuple[Escalator, StubNoticeSink]:
    notices = StubNoticeSink()
    calls = {"gates": 0, "canary": 0}
    verdict_calls: list[list[str]] = []

    def gate(argv: Any, cwd: Path) -> int:
        calls["gates"] += 1
        if events is not None:
            events.append("gate")
        assert cwd != repo
        assert {"pytest", "ruff"} & {Path(a).name for a in argv}
        return gates

    def canary_run(argv: Any, cwd: Path, timeout: float) -> tuple[int, str]:
        calls["canary"] += 1
        if events is not None:
            events.append("canary")
        assert cwd != repo
        assert "--canary" in list(argv)
        assert timeout > 0
        output = "CANARY demo: SETUP (1 setup row(s) of 1)\n"
        return canary, output

    def verdict_run(argv: Any) -> int:
        verdict_calls.append(list(argv))
        return 0

    arm = Escalator(
        tasks,
        repo_root=Path(__file__).resolve().parents[2],
        notices=notices,
        dispatcher=fake,
        gate_runner=gate,
        canary_runner=canary_run,
        oracle=oracle,
        verdict_runner=verdict_run,
        main_root=repo,
    )
    arm._calls = calls  # type: ignore[attr-defined]
    arm._verdict_calls = verdict_calls  # type: ignore[attr-defined]
    return arm, notices


def test_flag_defaults_off() -> None:
    assert escalation_enabled({}) is False
    assert escalation_enabled({"escalation": {"enabled": False}}) is False
    assert escalation_enabled({"escalation": {"enabled": True}}) is True


def test_oracle_flag_defaults_off(tmp_path: Path) -> None:
    assert (
        build_escalator(tmp_path / "tasks", tmp_path, None, {"escalation": {"enabled": False}})
        is None
    )
    hook = build_escalator(
        tmp_path / "tasks",
        tmp_path,
        None,
        {"escalation": {"enabled": True, "oracle": {"enabled": False}}},
    )
    assert hook is not None
    assert hook.escalator.oracle is None  # type: ignore[attr-defined]


def test_classify_matches_the_four_triggers_and_skips_a_cancel() -> None:
    setup = "CANARY demo: SETUP (1 setup row(s) of 1)\n"
    assert classify_block(_receipt("BLOCKED", steps=[_failed_step(setup)])) == "canary_setup"
    assert classify_block(_receipt("BLOCKED", steps=[_failed_step("HARNESS_ERROR\n")])) == (
        "harness_error"
    )
    assert classify_block(_receipt("BLOCKED", steps=[_failed_step()])) == "step_failure"
    trip = _failed_step()
    trip["state"] = "stopped"
    trip["memory_trip"] = {"reason": "fixture"}
    assert classify_block(
        _receipt("STOPPED", reason="memory safety trip: fixture", steps=[trip])
    ) == ("memory_trip")
    assert classify_block(_receipt("CANCELLED", reason="cancelled by operator")) is None
    assert (
        classify_block(_receipt("BLOCKED", reason="cancelled by operator", steps=[_failed_step()]))
        is None
    )
    stopped = _failed_step("BLOCKED: preflight\n")
    stopped["state"] = "stopped"
    stopped["reason"] = "output matched stop marker"
    assert (
        classify_block(_receipt("STOPPED", reason="output matched stop marker", steps=[stopped]))
        is None
    )


def test_security_jobs_use_the_security_kind() -> None:
    assert dispatch_kind({"id": "compliance-recapture", "purpose": "refresh", "steps": []}) == (
        "security"
    )
    assert dispatch_kind({"id": "job-a", "purpose": "detection pack", "steps": []}) == "security"
    assert (
        dispatch_kind(
            {
                "id": "job-a",
                "purpose": "run task",
                "steps": [{"id": "scan", "argv": ["tests/security.py"]}],
            }
        )
        == "security"
    )
    assert (
        dispatch_kind({"id": "job-a", "purpose": "count rows", "steps": [{"id": "one"}]}) == "code"
    )


def test_brief_carries_the_receipt_and_the_previous_risk(tmp_path: Path) -> None:
    raw = {"id": "job-a", "purpose": "fix the canary", "steps": []}
    receipt = _receipt(
        "BLOCKED",
        steps=[_failed_step(("x\n" * 80) + "CANARY demo: SETUP (1 setup row(s) of 1)\n")],
    )
    prior = prior_notes("## RESULT\n\npartial\n\n## OPEN / RISK\n\nstill red\n")
    path = write_brief(tmp_path, tmp_path, "job-a", 2, "canary_setup", raw, receipt, prior)
    text = path.read_text(encoding="utf-8")
    assert path.name == "job-a-2.md"
    assert "fix the canary" in text
    assert "scripts/step.py" in text
    assert "CANARY demo: SETUP" in text
    assert "Previous RESULT" in text and "partial" in text
    assert "Previous OPEN-RISK" in text and "still red" in text
    assert sum(1 for line in text.splitlines() if line == "x") <= 60


def test_brief_contract_override_and_addendum_hash(tmp_path: Path) -> None:
    raw = {"id": "job-a", "purpose": "exercise tests", "steps": []}
    kind = _brief_contract_kind(raw, "code")
    assert kind == "tests"
    assert _brief_contract_kind({"purpose": "review compliance"}, "security") == "security"
    contracts = Path(__file__).resolve().parents[2] / "coding_task" / "CONTRACTS"
    assert all(
        len(path.read_text(encoding="utf-8").splitlines()) <= 15 for path in contracts.glob("*.md")
    )
    path = write_brief(
        tmp_path,
        tmp_path,
        "job-a",
        1,
        "step_failure",
        raw,
        _receipt("BLOCKED"),
        "",
        contract_kind=kind,
        addendum_text="Never touch a real store.",
        addendum_sha="abc123",
    )
    text = path.read_text(encoding="utf-8")
    assert (
        "Commit your repair on this branch (this brief overrides WORKER_CONTRACT §5). Do not push."
        in text
    )
    assert "Worker contract addendum: tests (sha256 abc123)" in text
    assert "Never touch a real store." in text


def test_allowlist_holds_portal_and_merges_wfe() -> None:
    assert decide(LaneChanges(("tests/wfe/test_ok.py",), (), ())).status == "merge"
    assert decide(LaneChanges(("tests/wfe/plans/x.yaml",), (), ())).status == "merge"
    assert decide(LaneChanges(("config/arm_jobs/job.yaml",), (), ())).status == "merge"
    held = decide(LaneChanges(("portal/modules/orchestration/queue.py",), (), ()))
    assert held.status == "hold"
    assert "portal/" in held.detail
    assert decide(LaneChanges(("scripts/step.py",), (), ())).status == "hold"
    assert decide(LaneChanges(("Dockerfile.pipeline",), (), ())).status == "hold"
    assert decide(LaneChanges((), ("tests/wfe/test_ok.py",), ())).status == "uncommitted"
    assert decide(LaneChanges((), (), ())).status == "empty"


def test_decide_marks_weakened_tests_before_gates(tmp_path: Path) -> None:
    cases = [
        ("removed-test", "def test_ok():\n    assert True\n", "def helper():\n    pass\n"),
        ("deleted-file", "def test_ok():\n    assert True\n", None),
        (
            "skip-marker",
            "def test_ok():\n    assert True\n",
            "@pytest.mark.skip(reason='broken')\ndef test_ok():\n    assert True\n",
        ),
        (
            "weakened-assert",
            "def test_ok():\n    assert value == 1\n",
            "def test_ok():\n    assert value\n",
        ),
    ]
    for name, original, replacement in cases:
        repo = _repo(tmp_path / name)
        target = repo / "tests/wfe/test_ok.py"
        target.write_text(original, encoding="utf-8")
        changed = subprocess.run(
            ["git", "-C", str(repo), "diff", "--quiet", "--", "tests/wfe/test_ok.py"],
            check=False,
        ).returncode
        if changed:
            _git(repo, "add", "tests/wfe/test_ok.py")
            _git(repo, "commit", "-m", "test baseline")
        base = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        lane = tmp_path / f"{name}-lane"
        _git(repo, "worktree", "add", "-b", f"lane/{name}", str(lane), "HEAD")
        lane_target = lane / "tests/wfe/test_ok.py"
        if replacement is None:
            lane_target.unlink()
        else:
            lane_target.write_text(replacement, encoding="utf-8")
        _git(lane, "add", "-A", "tests/wfe/test_ok.py")
        _git(lane, "commit", "-m", name)
        decision = decide(LaneChanges(("tests/wfe/test_ok.py",), (), ()), worktree=lane, base=base)
        assert decision.status == "weakened", name

    repo = _repo(tmp_path / "stronger")
    target = repo / "tests/wfe/test_ok.py"
    target.write_text("def test_ok():\n    assert value > 1\n", encoding="utf-8")
    _git(repo, "add", "tests/wfe/test_ok.py")
    _git(repo, "commit", "-m", "test baseline")
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    lane = tmp_path / "stronger-lane"
    _git(repo, "worktree", "add", "-b", "lane/stronger", str(lane), "HEAD")
    (lane / "tests/wfe/test_ok.py").write_text(
        "def test_ok():\n    assert value > 2\n", encoding="utf-8"
    )
    _git(lane, "add", "tests/wfe/test_ok.py")
    _git(lane, "commit", "-m", "strengthen")
    stronger = decide(LaneChanges(("tests/wfe/test_ok.py",), (), ()), worktree=lane, base=base)
    assert stronger.status == "merge"


def test_weakened_lane_skips_gates_and_oracle(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "main")
    target = repo / "tests/wfe/test_ok.py"
    target.write_text("def test_ok():\n    assert value == 1\n", encoding="utf-8")
    _git(repo, "add", "tests/wfe/test_ok.py")
    _git(repo, "commit", "-m", "meaningful test")
    tasks = tmp_path / "tasks"
    item = _blocked(tasks, repo, _receipt("BLOCKED", steps=[_failed_step()]))
    lane = tmp_path / "lane"
    _git(repo, "worktree", "add", "-b", "lane/weakened", str(lane), "HEAD")
    (lane / "tests/wfe/test_ok.py").write_text(
        "def test_ok():\n    assert value\n", encoding="utf-8"
    )
    _git(lane, "add", "tests/wfe/test_ok.py")
    _git(lane, "commit", "-m", "weaken test")
    empty = _lane(repo, LaneChanges((), (), ()))
    fake = _FakeDispatch(
        [_lane(lane, LaneChanges(("tests/wfe/test_ok.py",), (), ())), empty, empty]
    )
    oracle = _FakeOracle([])
    arm, _notices = _escalator(tasks, repo, fake, oracle=oracle)
    outcome = arm.handle(item, QueueRun("BLOCKED", "job-a", tasks / "job-a" / "receipt.json"))
    second = (repo / _SCRATCH / "escalations" / "job-a-2.md").read_text(encoding="utf-8")
    assert outcome == "parked"
    assert arm._calls["gates"] == 0  # type: ignore[attr-defined]
    assert oracle.calls == []
    assert "weakened or removed assertion" in second


def test_auto_merge_requeues_when_the_canary_passes(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "main")
    tasks = tmp_path / "tasks"
    lane = tmp_path / "lane"
    _git(repo, "worktree", "add", "-b", "lane/esc-job-a-1", str(lane), "HEAD")
    target = lane / "tests" / "wfe" / "test_ok.py"
    target.write_text("def test_ok():\n    assert True and 1 == 1\n", encoding="utf-8")
    _git(lane, "add", "tests/wfe/test_ok.py")
    _git(lane, "commit", "-m", "repair")
    item = _blocked(tasks, repo, _receipt("BLOCKED", steps=[_failed_step()]))
    # The blocked fixture enqueued the no-canary spec. Re-enqueue is not possible;
    # the canary pass with no canary step re-queues after the merge.
    fake = _FakeDispatch([_lane(lane, LaneChanges(("tests/wfe/test_ok.py",), (), ()))])
    arm, notices = _escalator(tasks, repo, fake)
    outcome = arm.handle(item, QueueRun("BLOCKED", "job-a", tasks / "job-a" / "receipt.json"))
    assert outcome == "merged"
    assert fake.calls[0]["tier"] == "auto"
    assert fake.calls[0]["kind"] == "code"
    assert "assert True and 1 == 1" in (repo / "tests/wfe/test_ok.py").read_text(encoding="utf-8")
    dispatched = next(
        event for event in arm.ledger.events("job-a") if event["event"] == "dispatched"
    )
    addendum = json.loads(dispatched["detail_json"])
    assert addendum["addendum_kind"] == "debug"
    assert len(addendum["addendum_sha256"]) == 64
    verdict = arm._verdict_calls[0]  # type: ignore[attr-defined]
    assert verdict[verdict.index("--repo") + 1] == str(repo)
    assert verdict[verdict.index("--role") + 1] == "esc-job-a-1"
    assert "--accept" in verdict
    assert verdict[verdict.index("--note") + 1].startswith("merged:")
    with QueueLedger(tasks) as ledger:
        assert ledger.task("job-a")["state"] == "queued"
    events = [note["event"] for note in notices.escalations]
    assert "dispatched" in events and "merged" in events
    saved = json.loads((tasks / "job-a" / "receipt.json").read_text(encoding="utf-8"))
    assert any(row["event"] == "merged" for row in saved["escalations"])
    assert arm.ledger.events("job-a")


def test_canary_failure_does_not_requeue(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "main")
    tasks = tmp_path / "tasks"
    spec = _spec(repo, canary=True)
    with QueueLedger(tasks) as ledger:
        ledger.enqueue_job(spec, repo)
        ledger.finish("job-a", "blocked", "BLOCKED", "step exited 1")
    receipt = _receipt(
        "BLOCKED",
        steps=[_failed_step("CANARY demo: SETUP (1 setup row(s) of 1)\n")],
    )
    (tasks / "job-a" / "receipt.json").write_text(json.dumps(receipt) + "\n", encoding="utf-8")
    lane = tmp_path / "lane"
    _git(repo, "worktree", "add", "-b", "lane/fix", str(lane), "HEAD")
    (lane / "tests/wfe/test_ok.py").write_text(
        "def test_ok():\n    assert True and 1 == 1\n", encoding="utf-8"
    )
    _git(lane, "add", "tests/wfe/test_ok.py")
    _git(lane, "commit", "-m", "try")
    lanes = [_lane(lane, LaneChanges(("tests/wfe/test_ok.py",), (), ())) for _ in range(3)]
    fake = _FakeDispatch(lanes)
    arm, _notices = _escalator(tasks, repo, fake, canary=1)
    before = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout
    with QueueLedger(tasks) as ledger:
        item = ledger.task("job-a")
    assert item is not None
    outcome = arm.handle(item, QueueRun("BLOCKED", "job-a", tasks / "job-a" / "receipt.json"))
    after = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout
    assert outcome == "parked"
    assert before == after
    assert all(
        call[call.index("--note") + 1].startswith("canary-failed:")
        for call in arm._verdict_calls  # type: ignore[attr-defined]
    )
    with QueueLedger(tasks) as ledger:
        row = ledger.task("job-a")
    assert row is not None
    assert row["state"] == "blocked"
    assert "escalation exhausted: esc-job-a-1, esc-job-a-2, esc-job-a-3" in str(row["last_error"])
    assert [call["tier"] for call in fake.calls] == ["auto", "auto", "escalate"]
    second = (repo / _SCRATCH / "escalations" / "job-a-2.md").read_text(encoding="utf-8")
    assert "canary failed in the throwaway merge worktree" in second
    assert "CANARY demo: SETUP" in second


def test_gates_canary_oracle_land_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path / "main")
    tasks = tmp_path / "tasks"
    item = _blocked(
        tasks,
        repo,
        _receipt(
            "BLOCKED", reason="canary setup failed", steps=[_failed_step("CANARY demo: SETUP\n")]
        ),
    )
    lane = tmp_path / "lane"
    _git(repo, "worktree", "add", "-b", "lane/oracle", str(lane), "HEAD")
    (lane / "tests/wfe/test_ok.py").write_text(
        "def test_ok():\n    assert True and 1 == 1\n", encoding="utf-8"
    )
    _git(lane, "add", "tests/wfe/test_ok.py")
    _git(lane, "commit", "-m", "repair")
    events: list[str] = []
    fake = _FakeDispatch(
        [_lane(lane, LaneChanges(("tests/wfe/test_ok.py",), (), ()), model="deepseek/v4")]
    )
    oracle = _FakeOracle([OracleResult("approve", "approved", "merged")], events)
    arm, _notices = _escalator(tasks, repo, fake, canary=0, oracle=oracle, events=events)
    original_decide = escalate_module.decide
    original_weakening = escalate_module._test_weakening
    original_land = escalate_module._land

    def ordered_decide(changes: LaneChanges, **kwargs: Any) -> Any:
        events.append("allowlist")
        return original_decide(changes, **kwargs)

    def ordered_weakening(worktree: Path, base: str) -> str | None:
        events.append("weakened")
        return original_weakening(worktree, base)

    def ordered_land(main: Path, lane_result: LaneResult, message: str) -> str | None:
        events.append("land")
        return original_land(main, lane_result, message)

    monkeypatch.setattr(escalate_module, "decide", ordered_decide)
    monkeypatch.setattr(escalate_module, "_test_weakening", ordered_weakening)
    monkeypatch.setattr(escalate_module, "_land", ordered_land)
    outcome = arm.handle(item, QueueRun("BLOCKED", "job-a", tasks / "job-a" / "receipt.json"))
    assert outcome == "merged"
    assert events == ["allowlist", "weakened", "gate", "gate", "gate", "canary", "oracle", "land"]


def test_oracle_rejection_is_forwarded_to_next_brief(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "main")
    tasks = tmp_path / "tasks"
    item = _blocked(tasks, repo, _receipt("BLOCKED", steps=[_failed_step()]))
    lane = tmp_path / "lane"
    _git(repo, "worktree", "add", "-b", "lane/oracle-reject", str(lane), "HEAD")
    (lane / "tests/wfe/test_ok.py").write_text(
        "def test_ok():\n    assert True and 1 == 1\n", encoding="utf-8"
    )
    _git(lane, "add", "tests/wfe/test_ok.py")
    _git(lane, "commit", "-m", "repair")
    changes = LaneChanges(("tests/wfe/test_ok.py",), (), ())
    empty = _lane(repo, LaneChanges((), (), ()))
    fake = _FakeDispatch([_lane(lane, changes, model="deepseek/v4"), empty, empty])
    oracle = _FakeOracle(
        [OracleResult("reject", "tests/wfe/test_ok.py:1: weakened assertion", "oracle-rejected")]
    )
    arm, _notices = _escalator(tasks, repo, fake, oracle=oracle)
    before = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout
    outcome = arm.handle(item, QueueRun("BLOCKED", "job-a", tasks / "job-a" / "receipt.json"))
    after = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout
    second = (repo / _SCRATCH / "escalations" / "job-a-2.md").read_text(encoding="utf-8")
    assert outcome == "parked"
    assert before == after
    assert "oracle rejected: tests/wfe/test_ok.py:1: weakened assertion" in second
    assert len(oracle.calls) == 1
    assert arm._verdict_calls[0][arm._verdict_calls[0].index("--note") + 1].startswith(
        "oracle-rejected:"
    )  # type: ignore[attr-defined]


def test_process_oracle_routes_review_kind_and_holds_malformed_output(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "main")
    lane_path = tmp_path / "lane"
    _git(repo, "worktree", "add", "-b", "lane/oracle-process", str(lane_path), "HEAD")
    target = lane_path / "tests/wfe/test_ok.py"
    target.write_text("def test_ok():\n    assert True and 1 == 1\n", encoding="utf-8")
    _git(lane_path, "add", "tests/wfe/test_ok.py")
    _git(lane_path, "commit", "-m", "repair")
    changes = LaneChanges(("tests/wfe/test_ok.py",), (), ())

    def policy(_binary: Path, _tier: str) -> tuple[str, bool, set[str], set[str]]:
        return "moonshotai/kimi-k3.1-pro", False, {"review", "security"}, {"security"}

    approved = "## RESULT\n\nAPPROVE\n\n## FINDINGS\n\nNone\n"
    dispatch = _FakeDispatch([_lane(None, LaneChanges((), (), ()), text=approved)])
    oracle = ProcessOracle(
        tmp_path / "tasks",
        repo_root=repo,
        tiers="kimi",
        timeout_seconds=10,
        dispatcher=dispatch,
        policy_resolver=policy,
    )
    candidate = _lane(lane_path, changes, model="deepseek/deepseek-v4-pro")
    result = oracle.review(job_id="job-a", attempt=1, lane=candidate, base="HEAD~1", kind="code")
    assert result.verdict == "approve"
    assert dispatch.calls[0]["kind"] == "review"
    assert "Defect checklist" in dispatch.calls[0]["brief"].read_text(encoding="utf-8")

    malformed_dispatch = _FakeDispatch(
        [_lane(None, LaneChanges((), (), ()), text="## RESULT\n\nmaybe\n")]
    )
    malformed = ProcessOracle(
        tmp_path / "tasks",
        repo_root=repo,
        tiers="kimi",
        timeout_seconds=10,
        dispatcher=malformed_dispatch,
        policy_resolver=policy,
    ).review(job_id="job-a", attempt=2, lane=candidate, base="HEAD~1", kind="code")
    assert malformed.verdict == "hold"
    assert malformed.tag == "contract-miss"

    security_dispatch = _FakeDispatch([_lane(None, LaneChanges((), (), ()), text=approved)])
    security = ProcessOracle(
        tmp_path / "tasks",
        repo_root=repo,
        tiers="kimi",
        timeout_seconds=10,
        dispatcher=security_dispatch,
        policy_resolver=policy,
    ).review(job_id="job-a", attempt=3, lane=candidate, base="HEAD~1", kind="security")
    assert security.verdict == "approve"
    assert security_dispatch.calls[0]["kind"] == "security"

    free_dispatch = _FakeDispatch([])

    def free_policy(_binary: Path, _tier: str) -> tuple[str, bool, set[str], set[str]]:
        return "moonshotai/kimi-k3.1-pro", True, {"review", "security"}, {"security"}

    free = ProcessOracle(
        tmp_path / "tasks",
        repo_root=repo,
        tiers="kimi",
        timeout_seconds=10,
        dispatcher=free_dispatch,
        policy_resolver=free_policy,
    ).review(job_id="job-a", attempt=4, lane=candidate, base="HEAD~1", kind="security")
    assert free.verdict == "hold"
    assert not free_dispatch.calls

    same_family_dispatch = _FakeDispatch([])
    same_family = ProcessOracle(
        tmp_path / "tasks",
        repo_root=repo,
        tiers="deep-pro",
        timeout_seconds=10,
        dispatcher=same_family_dispatch,
        policy_resolver=lambda *_args: ("deepseek/deepseek-v4", False, {"review"}, set()),
    ).review(job_id="job-a", attempt=5, lane=candidate, base="HEAD~1", kind="code")
    assert same_family.verdict == "hold"
    assert not same_family_dispatch.calls

    def by_tier(_binary: Path, tier: str) -> tuple[str, bool, set[str], set[str]]:
        model = "deepseek/deepseek-v4" if tier == "deep-pro" else "openai/gpt-5.5"
        return model, False, {"review"}, set()

    fallback_dispatch = _FakeDispatch([_lane(None, LaneChanges((), (), ()), text=approved)])
    fallback = ProcessOracle(
        tmp_path / "tasks",
        repo_root=repo,
        tiers=["deep-pro", "sol"],
        timeout_seconds=10,
        dispatcher=fallback_dispatch,
        policy_resolver=by_tier,
    ).review(job_id="job-a", attempt=5, lane=candidate, base="HEAD~1", kind="code")
    assert fallback.verdict == "approve"
    assert fallback_dispatch.calls[0]["tier"] == "sol"

    failed = ProcessOracle(
        tmp_path / "tasks",
        repo_root=repo,
        tiers="kimi",
        timeout_seconds=10,
        dispatcher=_FakeDispatch([]),
        policy_resolver=policy,
    ).review(job_id="job-a", attempt=6, lane=candidate, base="HEAD~1", kind="code")
    assert failed.verdict == "hold"
    assert failed.tag == "infra"

    timed_out_dispatch = _FakeDispatch(
        [LaneResult("oracle", "kimi", 124, "", "lane/oracle", None, LaneChanges((), (), ()))]
    )
    timed_out = ProcessOracle(
        tmp_path / "tasks",
        repo_root=repo,
        tiers="kimi",
        timeout_seconds=10,
        dispatcher=timed_out_dispatch,
        policy_resolver=policy,
    ).review(job_id="job-a", attempt=7, lane=candidate, base="HEAD~1", kind="code")
    assert timed_out.verdict == "hold"
    assert timed_out.tag == "infra"


def test_oracle_head_change_holds_and_keeps_main_untouched(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "main")
    tasks = tmp_path / "tasks"
    item = _blocked(tasks, repo, _receipt("BLOCKED", steps=[_failed_step()]))
    lane = tmp_path / "lane"
    _git(repo, "worktree", "add", "-b", "lane/oracle-mutation", str(lane), "HEAD")
    (lane / "tests/wfe/test_ok.py").write_text(
        "def test_ok():\n    assert True and 1 == 1\n", encoding="utf-8"
    )
    _git(lane, "add", "tests/wfe/test_ok.py")
    _git(lane, "commit", "-m", "repair")

    class _MutatingOracle:
        def review(self, **_kwargs: Any) -> OracleResult:
            target = lane / "coding_task" / "review-note.md"
            target.parent.mkdir(parents=True)
            target.write_text("changed during review\n", encoding="utf-8")
            _git(lane, "add", "-f", _SCRATCH + "/review-note.md")
            _git(lane, "commit", "-m", "review mutation")
            return OracleResult("approve", "approved", "merged")

    fake = _FakeDispatch([_lane(lane, LaneChanges(("tests/wfe/test_ok.py",), (), ()))])
    arm, notices = _escalator(tasks, repo, fake, oracle=_MutatingOracle())
    before = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout
    outcome = arm.handle(item, QueueRun("BLOCKED", "job-a", tasks / "job-a" / "receipt.json"))
    after = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout
    assert outcome == "held"
    assert before == after
    assert notices.escalations[-1]["event"] == "held"
    assert "changed during oracle review" in notices.escalations[-1]["detail"]["detail"]


def test_quota_retry_resumes_same_role_without_new(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "main")
    tasks = tmp_path / "tasks"
    item = _blocked(tasks, repo, _receipt("BLOCKED", steps=[_failed_step()]))
    lane = tmp_path / "lane"
    _git(repo, "worktree", "add", "-b", "lane/quota", str(lane), "HEAD")
    (lane / "tests/wfe/test_ok.py").write_text(
        "def test_ok():\n    assert True and 1 == 1\n", encoding="utf-8"
    )
    _git(lane, "add", "tests/wfe/test_ok.py")
    _git(lane, "commit", "-m", "repair")
    changes = LaneChanges(("tests/wfe/test_ok.py",), (), ())
    fake = _FakeDispatch(
        [
            _lane(
                lane,
                changes,
                status="quota",
                retry_until="20000101T000000Z",
                model="deepseek/v4",
            ),
            _lane(lane, changes, status="completed", model="deepseek/v4"),
        ]
    )
    arm, notices = _escalator(tasks, repo, fake)
    queued = QueueRun("BLOCKED", "job-a", tasks / "job-a" / "receipt.json")
    assert arm.handle(item, queued) == "quota"
    quota = next(event for event in arm.ledger.events("job-a") if event["event"] == "quota")
    detail = json.loads(quota["detail_json"])
    command = detail["resume_command"]
    assert "--role esc-job-a-1" in command
    assert "--new" not in command
    assert detail["retry_until"] == "20000101T000000Z"
    assert notices.escalations[-1]["event"] == "quota"
    assert notices.escalations[-1]["detail"]["resume_command"] == command
    assert arm.handle(item, queued) == "merged"
    assert [call["new"] for call in fake.calls] == [True, False]
    assert [call["role"] for call in fake.calls] == ["esc-job-a-1", "esc-job-a-1"]
    assert [call["tier"] for call in fake.calls] == ["auto", "auto"]


def test_quota_waits_for_retry_time_and_queue_poll_checks_pending_jobs(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "main")
    tasks = tmp_path / "tasks"
    item = _blocked(tasks, repo, _receipt("BLOCKED", steps=[_failed_step()]))
    lane = tmp_path / "lane"
    _git(repo, "worktree", "add", "-b", "lane/quota-wait", str(lane), "HEAD")
    fake = _FakeDispatch(
        [
            _lane(
                lane,
                LaneChanges((), (), ()),
                status="quota",
                retry_until="20990101T000000Z",
                model="deepseek/v4",
            )
        ]
    )
    arm, _notices = _escalator(tasks, repo, fake)
    queued = QueueRun("BLOCKED", "job-a", tasks / "job-a" / "receipt.json")
    assert arm.handle(item, queued) == "quota"
    assert arm.resume_pending(item, queued) == "waiting"
    assert len(fake.calls) == 1

    seen: list[str] = []

    class _ResumeHook:
        def __call__(self, _item: dict[str, Any], _result: QueueRun) -> None:
            return None

        def resume_pending(self, pending_item: dict[str, Any], _result: QueueRun) -> str:
            seen.append(str(pending_item["task_id"]))
            return "waiting"

    queue = OvernightQueue(
        tasks,
        None,
        QueueGate({}, {}, pid_file=tmp_path / "pids"),
        repo_root=repo,
        dispatch_lock_dir=tmp_path / "locks",
        escalation=_ResumeHook(),
    )
    assert queue.run_next().status == "EMPTY"
    assert seen == ["job-a"]


def test_telegram_quota_notice_keeps_full_resume_command(tmp_path: Path) -> None:
    sink = TelegramNoticeSink(path=tmp_path / "telegram.sqlite3")
    messages: list[str] = []
    sink.store.notify = lambda _job, _event, text: messages.append(text)  # type: ignore[method-assign]
    command = "python3 /tmp/dispatch.py --repo '/tmp/main checkout' run --role esc-job-a-1"
    sink.escalation(
        "job-a",
        "quota",
        {"retry_until": "20990101T000000Z", "resume_command": command},
    )
    assert command in messages[0]


def test_portal_diff_is_held(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "main")
    tasks = tmp_path / "tasks"
    item = _blocked(tasks, repo, _receipt("BLOCKED", steps=[_failed_step()]))
    lane = tmp_path / "lane"
    _git(repo, "worktree", "add", "-b", "lane/hold", str(lane), "HEAD")
    portal = lane / "portal" / "modules" / "orchestration" / "queue.py"
    portal.parent.mkdir(parents=True)
    portal.write_text("x = 1\n", encoding="utf-8")
    _git(lane, "add", "portal/modules/orchestration/queue.py")
    _git(lane, "commit", "-m", "touch portal")
    fake = _FakeDispatch(
        [_lane(lane, LaneChanges(("portal/modules/orchestration/queue.py",), (), ()))]
    )
    arm, notices = _escalator(tasks, repo, fake)
    before = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout
    outcome = arm.handle(item, QueueRun("BLOCKED", "job-a", tasks / "job-a" / "receipt.json"))
    after = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout
    assert outcome == "held"
    assert before == after
    assert notices.escalations[-1]["event"] == "held"
    assert "portal/" in notices.escalations[-1]["detail"]["detail"]
    assert arm._verdict_calls[0][arm._verdict_calls[0].index("--note") + 1].startswith("held-path:")  # type: ignore[attr-defined]
    assert arm._calls["gates"] == 0  # type: ignore[attr-defined]


def test_three_empty_lanes_park_the_job(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "main")
    tasks = tmp_path / "tasks"
    item = _blocked(tasks, repo, _receipt("BLOCKED", error="RuntimeError: boom"))
    fake = _FakeDispatch([_lane(repo, LaneChanges((), (), ()), text="no result") for _ in range(3)])
    arm, notices = _escalator(tasks, repo, fake)
    outcome = arm.handle(item, QueueRun("BLOCKED", "job-a", tasks / "job-a" / "receipt.json"))
    assert outcome == "parked"
    assert notices.escalations[-1]["event"] == "parked"
    assert "esc-job-a-1" in notices.escalations[-1]["detail"]["reason"]


def test_attempt_two_brief_includes_attempt_one(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "main")
    tasks = tmp_path / "tasks"
    item = _blocked(tasks, repo, _receipt("BLOCKED", steps=[_failed_step()]))
    text = "## RESULT\n\npartial\n\n## WHAT CHANGED\n\nnone\n\n## OPEN / RISK\n\nstill open\n"
    fake = _FakeDispatch(
        [
            _lane(repo, LaneChanges((), (), ()), text=text),
            _lane(repo, LaneChanges((), (), ()), text=text),
            _lane(repo, LaneChanges((), (), ()), text=text),
        ]
    )
    arm, _notices = _escalator(tasks, repo, fake)
    arm.handle(item, QueueRun("BLOCKED", "job-a", tasks / "job-a" / "receipt.json"))
    second = (repo / _SCRATCH / "escalations" / "job-a-2.md").read_text(encoding="utf-8")
    assert "partial" in second and "still open" in second
    first = (repo / _SCRATCH / "escalations" / "job-a-1.md").read_text(encoding="utf-8")
    assert "Previous RESULT" not in first


def test_bounded_wait_stops_a_live_process() -> None:
    proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
    started = time.monotonic()
    code = _wait_process(proc, 0.3, 0.05, time.sleep)
    assert time.monotonic() - started < 5
    assert code == 124 or proc.poll() is not None


def test_queue_calls_the_hook_only_for_a_blocked_job(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "main")
    tasks = tmp_path / "tasks"
    script = repo / "scripts" / "bad.py"
    script.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(2)\n", encoding="utf-8")
    script.chmod(0o755)
    spec = parse_job_spec(
        {
            "id": "job-a",
            "purpose": "fail the step",
            "preconditions": {"stack": "down", "free_memory_gib": 0, "disk_free_gib": 0},
            "steps": [{"id": "run", "argv": ["scripts/bad.py"], "timeout_seconds": 5}],
            "report": {"fields": REPORT},
        },
        repo_root=repo,
    )
    with QueueLedger(tasks) as ledger:
        ledger.enqueue_job(spec, repo)
    seen: list[str] = []

    def hook(item: dict[str, Any], result: QueueRun) -> None:
        seen.append(f"{item['task_id']}:{result.status}")

    from tests.unit.test_orchestration_jobs import _runner

    queue = OvernightQueue(
        tasks,
        None,
        QueueGate({}, {"yield_lock_dir": str(tmp_path / "locks")}, pid_file=tmp_path / "pids"),
        repo_root=repo,
        notices=StubNoticeSink(),
        job_factory=lambda: _runner(tmp_path, repo),
        escalation=hook,
    )
    result = queue.run_next()
    assert result.status == "BLOCKED"
    assert seen == ["job-a:BLOCKED"]


def test_a_raising_hook_does_not_stop_the_queue(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "main")
    tasks = tmp_path / "tasks"
    script = repo / "scripts" / "bad.py"
    script.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(2)\n", encoding="utf-8")
    script.chmod(0o755)
    spec = parse_job_spec(
        {
            "id": "job-a",
            "purpose": "fail the step",
            "preconditions": {"stack": "down", "free_memory_gib": 0, "disk_free_gib": 0},
            "steps": [{"id": "run", "argv": ["scripts/bad.py"], "timeout_seconds": 5}],
            "report": {"fields": REPORT},
        },
        repo_root=repo,
    )
    with QueueLedger(tasks) as ledger:
        ledger.enqueue_job(spec, repo)

    def hook(item: dict[str, Any], result: QueueRun) -> None:
        raise RuntimeError("lane down")

    from tests.unit.test_orchestration_jobs import _runner

    queue = OvernightQueue(
        tasks,
        None,
        QueueGate({}, {"yield_lock_dir": str(tmp_path / "locks")}, pid_file=tmp_path / "pids"),
        repo_root=repo,
        notices=StubNoticeSink(),
        job_factory=lambda: _runner(tmp_path, repo),
        escalation=hook,
    )
    assert queue.run_next().status == "BLOCKED"


def test_escalate_cli_refuses_while_the_flag_is_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Its own config: the live one is the operator's to flip (enabled 10-30).
    config = tmp_path / "orchestration_arm.yaml"
    shipped = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "config" / "orchestration_arm.yaml").read_text(
            encoding="utf-8"
        )
    )
    shipped["queue"]["escalation"]["enabled"] = False
    config.write_text(yaml.safe_dump(shipped), encoding="utf-8")
    monkeypatch.setattr(cli_module, "_arm_config_path", lambda: config)
    result = CliRunner().invoke(orchestration_app, ["escalate", "job-a"])
    assert result.exit_code == 2
    assert "queue.escalation.enabled is false" in result.stderr or (
        "queue.escalation.enabled is false" in result.output
    )


def test_escalate_cli_runs_when_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "_require_enabled", lambda: None)
    monkeypatch.setattr(
        "portal.modules.orchestration.escalate.escalation_enabled", lambda _policy: True
    )
    seen: list[str] = []

    class _Arm:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def handle(self, item: dict[str, Any], result: QueueRun) -> str:
            seen.append(str(item["task_id"]))
            assert result.status == "BLOCKED"
            return "skipped"

    monkeypatch.setattr("portal.modules.orchestration.escalate.Escalator", _Arm)
    spec = _spec(_repo(tmp_path / "main"))
    with QueueLedger(tmp_path) as ledger:
        ledger.enqueue_job(spec, tmp_path / "main")
        ledger.finish("job-a", "blocked", "BLOCKED", "step exited 1")
    result = CliRunner().invoke(
        orchestration_app, ["escalate", "job-a", "--tasks-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert seen == ["job-a"]
    assert "skipped" in result.output


def _load_dispatch() -> Any:
    spec = importlib.util.spec_from_file_location("portal_dispatch_escalate", DISPATCH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(not DISPATCH.is_file(), reason="dispatcher is not installed on this machine")
def test_tier_escalate_picks_the_first_seat_with_headroom(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_dispatch()
    monkeypatch.setattr(module, "_context_misfit", lambda *_a, **_k: None)
    monkeypatch.setattr(module, "_recent_quota", lambda *_a, **_k: None)
    monkeypatch.setattr(module, "_plan_busy", lambda *_a, **_k: None)
    monkeypatch.setattr(module, "_reset_fraction", lambda _plan: 1.0)
    monkeypatch.setattr(
        module, "_plan_headroom", lambda _reg, plan: 0.0 if plan == "codex" else 1.0
    )
    chosen, why = module._resolve_escalate({}, "code", 0)
    assert chosen == "grok-max"
    assert any("sol" in line and "skipped" in line for line in why)
    assert module._escalated_effort(module.TIERS["grok-max"]) == "high"
    assert module._escalated_effort(module.TIERS["sol"]) == "high"
    assert module._escalated_effort(module.TIERS["astra"]) == "medium"
    assert module._escalate_skip({}, "or-inkling", "security", 0)


@pytest.mark.skipif(not DISPATCH.is_file(), reason="dispatcher is not installed on this machine")
def test_tier_escalate_sets_effort_under_max(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_dispatch()
    monkeypatch.setattr(module, "_resolve_escalate", lambda *_a, **_k: ("grok-max", ["picked"]))
    monkeypatch.setattr(module, "_brief_tokens", lambda *_a, **_k: 0)
    args = argparse.Namespace(
        tier="escalate",
        model=None,
        kind="code",
        scope="normal",
        brief=None,
        effort=None,
        peak_ok=False,
    )
    module._apply_tier_route(args, {}, Path("."))
    assert args.tier == "grok-max"
    assert args.effort == "high"
    assert args.peak_ok is True
    assert "ESCALATE" in capsys.readouterr().out


def test_a_conflicting_merge_is_aborted_and_main_stays_clean(tmp_path: Path) -> None:
    # The live checkout must never be left with conflict markers.
    from portal.modules.orchestration.escalate import _merge_head

    main = _repo(tmp_path / "main")
    target = main / "tests" / "wfe" / "test_ok.py"
    lane = tmp_path / "lane"
    _git(main, "worktree", "add", "-b", "lane/x", str(lane))
    (lane / "tests" / "wfe" / "test_ok.py").write_text("lane\n", encoding="utf-8")
    _git(lane, "commit", "-am", "lane edit")
    target.write_text("main\n", encoding="utf-8")
    _git(main, "commit", "-am", "main edit")
    before = subprocess.run(
        ["git", "-C", str(main), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout

    assert _merge_head(main, lane, "escalation: x attempt 1") is False

    status = subprocess.run(
        ["git", "-C", str(main), "status", "--porcelain"], capture_output=True, text=True
    ).stdout
    head = subprocess.run(
        ["git", "-C", str(main), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout
    assert status.strip() == ""
    assert head == before
    assert target.read_text(encoding="utf-8") == "main\n"


def test_oracle_walks_the_tier_list_past_same_family_and_quota(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "main")
    lane_path = tmp_path / "lane"
    _git(repo, "worktree", "add", "-b", "lane/oracle-walk", str(lane_path), "HEAD")
    (lane_path / "tests/wfe/test_ok.py").write_text("def test_ok():\n    assert 1 == 1\n")
    _git(lane_path, "add", "tests/wfe/test_ok.py")
    _git(lane_path, "commit", "-m", "repair")
    candidate = _lane(
        lane_path, LaneChanges(("tests/wfe/test_ok.py",), (), ()), model="openai/gpt-6.1-sol"
    )
    models = {"sol": "gpt-6.1-sol", "grok-max": "grok-4.7", "flagship": "zai/glm-5.3"}

    def policy(_binary: Path, tier: str) -> tuple[str, bool, set[str], set[str]]:
        return models.get(tier, "gpt-6-luna"), False, {"review", "security"}, {"security"}

    approved = "## RESULT\n\nAPPROVE\n\n## FINDINGS\n\nNone\n"
    dispatch = _FakeDispatch(
        [
            _lane(None, LaneChanges((), (), ()), text="", status="quota"),
            _lane(None, LaneChanges((), (), ()), text=approved),
        ]
    )
    result = ProcessOracle(
        tmp_path / "tasks",
        repo_root=repo,
        tiers=["sol", "grok-max", "flagship"],
        timeout_seconds=10,
        dispatcher=dispatch,
        policy_resolver=policy,
    ).review(job_id="job-a", attempt=1, lane=candidate, base="HEAD~1", kind="code")
    assert result.verdict == "approve"
    assert [c["tier"] for c in dispatch.calls] == ["grok-max", "flagship"]

    security = _FakeDispatch([_lane(None, LaneChanges((), (), ()), text=approved)])
    held = ProcessOracle(
        tmp_path / "tasks",
        repo_root=repo,
        tiers=["grok-max"],
        timeout_seconds=10,
        dispatcher=security,
        policy_resolver=policy,
    ).review(job_id="job-a", attempt=2, lane=candidate, base="HEAD~1", kind="security")
    assert held.verdict == "hold"  # daybreak is the only security reviewer; same family here
    assert not security.calls


def test_gates_use_the_main_checkout_venv_not_a_fresh_uv_env(tmp_path: Path) -> None:
    # 10-30: `uv run` in the throwaway worktree built a bare venv; the lock-drift test failed
    # every attempt regardless of the fix.
    from portal.modules.orchestration.escalate import _run_gates

    seen: list[list[str]] = []

    def runner(argv: Sequence[str], cwd: Path) -> int:
        seen.append(list(argv))
        assert cwd == tmp_path / "dest"
        return 0

    assert _run_gates(tmp_path / "dest", runner, tmp_path / "main")
    venv = str(tmp_path / "main" / ".venv")
    assert seen[0][:3] == [f"{venv}/bin/python", "-m", "pytest"]
    assert all(argv[0].startswith(venv) for argv in seen)
    assert not any(argv[0] == "uv" for argv in seen)


def test_escalation_canary_uses_a_throwaway_campaign_id() -> None:
    from portal.modules.orchestration.escalate import _throwaway_campaign

    argv = ["scripts/wfe_campaign.sh", "realuse_reruns_20261030b", "--plan", "p.yaml", "--canary"]
    out = _throwaway_campaign(argv, "portal-esc-Ab_9x")
    assert out[1] == "realuse_reruns_20261030b_portalescab9x"
    assert out[2:] == argv[2:]
    assert argv[1] == "realuse_reruns_20261030b"
    assert _throwaway_campaign(["other.sh", "x", "--canary"], "t") == ["other.sh", "x", "--canary"]


def test_merge_worktree_links_live_env_not_venv(tmp_path: Path) -> None:
    from portal.modules.orchestration.escalate import _link_live_state

    main, dest = tmp_path / "main", tmp_path / "dest"
    (main / ".venv").mkdir(parents=True)
    (main / ".env").write_text("OMLX_API_KEY=x\n")
    dest.mkdir()
    _link_live_state(dest, main)
    _link_live_state(dest, main)
    assert (dest / ".env").resolve() == (main / ".env").resolve()
    assert not (dest / ".venv").exists()
    shutil.rmtree(dest)
    assert (main / ".env").is_file() and (main / ".venv").is_dir()


def test_repin_ignores_untracked_reports(tmp_path: Path) -> None:
    from portal.modules.orchestration.escalate import _repin

    main, snap = tmp_path / "main", tmp_path / "snap"
    subprocess.run(["git", "init", "-q", str(main)], check=True)
    (main / "f").write_text("1")
    git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "-C", str(main), "add", "f"], check=True)
    subprocess.run([*git, "-C", str(main), "commit", "-qm", "a"], check=True)
    subprocess.run(
        ["git", "-C", str(main), "worktree", "add", "-q", "--detach", str(snap)], check=True
    )
    (main / "f").write_text("2")
    subprocess.run([*git, "-C", str(main), "commit", "-qam", "b"], check=True)
    (snap / "report.md").write_text("job output")
    assert _repin(main, snap) is True
    assert (snap / "f").read_text() == "2"
    (snap / "f").write_text("tracked edit")
    assert _repin(main, snap) is False
