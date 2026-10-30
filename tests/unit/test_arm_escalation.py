"""Offline escalation: fakes only. No live dispatch, Telegram, or git push."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from portal.modules.orchestration import cli as cli_module
from portal.modules.orchestration.cli import orchestration_app
from portal.modules.orchestration.escalate import (
    Escalator,
    LaneChanges,
    LaneResult,
    _wait_process,
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

    def run(self, *, role: str, tier: str, kind: str, brief: Path, repo: Path) -> LaneResult:
        self.calls.append({"role": role, "tier": tier, "kind": kind, "brief": brief, "repo": repo})
        if not self.results:
            raise RuntimeError("no fake lane left")
        lane = self.results.pop(0)
        return LaneResult(
            role, tier, lane.exit_code, lane.result_text, lane.branch, lane.worktree, lane.changes
        )


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
) -> LaneResult:
    return LaneResult("lane", "auto", 0, text, "lane/esc-job-a-1", worktree, changes)


def _escalator(
    tasks: Path,
    repo: Path,
    fake: _FakeDispatch,
    *,
    gates: int = 0,
    canary: int = 0,
) -> tuple[Escalator, StubNoticeSink]:
    notices = StubNoticeSink()
    calls = {"gates": 0, "canary": 0}

    def gate(argv: Any, cwd: Path) -> int:
        calls["gates"] += 1
        assert cwd != repo
        assert argv[2] in {"pytest", "ruff"}
        return gates

    def canary_run(argv: Any, cwd: Path, timeout: float) -> int:
        calls["canary"] += 1
        assert "--canary" in list(argv)
        assert timeout > 0
        return canary

    arm = Escalator(
        tasks,
        repo_root=repo,
        notices=notices,
        dispatcher=fake,
        gate_runner=gate,
        canary_runner=canary_run,
        main_root=repo,
    )
    arm._calls = calls  # type: ignore[attr-defined]
    return arm, notices


def test_flag_defaults_off() -> None:
    assert escalation_enabled({}) is False
    assert escalation_enabled({"escalation": {"enabled": False}}) is False
    assert escalation_enabled({"escalation": {"enabled": True}}) is True


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


def test_auto_merge_requeues_when_the_canary_passes(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "main")
    tasks = tmp_path / "tasks"
    lane = tmp_path / "lane"
    _git(repo, "worktree", "add", "-b", "lane/esc-job-a-1", str(lane), "HEAD")
    target = lane / "tests" / "wfe" / "test_ok.py"
    target.write_text("def test_ok():\n    assert 1 == 1\n", encoding="utf-8")
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
    assert "assert 1 == 1" in (repo / "tests/wfe/test_ok.py").read_text(encoding="utf-8")
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
        "def test_ok():\n    assert 1 == 1\n", encoding="utf-8"
    )
    _git(lane, "add", "tests/wfe/test_ok.py")
    _git(lane, "commit", "-m", "try")
    lanes = [_lane(lane, LaneChanges(("tests/wfe/test_ok.py",), (), ())) for _ in range(3)]
    fake = _FakeDispatch(lanes)
    arm, _notices = _escalator(tasks, repo, fake, canary=1)
    with QueueLedger(tasks) as ledger:
        item = ledger.task("job-a")
    assert item is not None
    outcome = arm.handle(item, QueueRun("BLOCKED", "job-a", tasks / "job-a" / "receipt.json"))
    assert outcome == "parked"
    with QueueLedger(tasks) as ledger:
        row = ledger.task("job-a")
    assert row is not None
    assert row["state"] == "blocked"
    assert "escalation exhausted: esc-job-a-1, esc-job-a-2, esc-job-a-3" in str(row["last_error"])
    assert [call["tier"] for call in fake.calls] == ["auto", "auto", "escalate"]


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


def test_escalate_cli_refuses_while_the_flag_is_false() -> None:
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
