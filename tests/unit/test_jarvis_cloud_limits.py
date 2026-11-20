"""Jarvis personal cloud dispatch: attempt cap, interrupted lanes, operator cancel.

No network: dispatcher fakes only, and the Telegram control store lives in tmp_path.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from portal.modules.orchestration import control
from portal.modules.orchestration.personal_intake import telegram_do_reply
from portal.modules.orchestration.personal_runner import (
    Completion,
    PersonalRun,
    poll_personal_tasks,
)
from portal.modules.orchestration.personal_store import PersonalStore
from portal_channels.telegram.arm_bridge import ArmTelegramStore


class _Caller:
    def __init__(self) -> None:
        self.recall_reply = Completion("No matching operator memory.", (), 1, ("recall",))

    def complete(self, body: dict[str, object]) -> Completion:
        if body.get("portal_bite_tools") == ["recall"]:
            return self.recall_reply
        return Completion("not JSON", (), 0)


class _PlanCaller(_Caller):
    def __init__(self, replies: list[Completion]) -> None:
        super().__init__()
        self.replies = list(replies)

    def complete(self, body: dict[str, object]) -> Completion:
        if not self.replies:
            raise AssertionError("unexpected extra Pipeline call")
        return self.replies.pop(0)


class _Sink:
    def __init__(self, path: Path) -> None:
        self.store = ArmTelegramStore(path)
        self.messages: list[str] = []

    def notify(self, task_id: str, kind: str, message: str) -> None:
        self.messages.append(message)


class _Dispatcher:
    def __init__(self, outcome: SimpleNamespace) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []

    def run(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return self.outcome


def _lane(exit_code: int, status: str) -> SimpleNamespace:
    return SimpleNamespace(exit_code=exit_code, status=status, model="mock", result_text="")


def _cloud_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sink: _Sink,
    dispatcher: object,
) -> PersonalRun | None:
    from portal.modules.orchestration import personal_runner

    monkeypatch.setattr(personal_runner, "_personal_cloud_enabled", lambda: True, raising=False)
    telegram_do_reply(tmp_path, 7, "help with an invalid local plan")
    first = poll_personal_tasks(tmp_path, sink, _Caller(), recall=lambda query: "")
    assert first is not None and first.status == "retrying"
    return poll_personal_tasks(
        tmp_path, sink, _Caller(), dispatcher=dispatcher, recall=lambda query: ""
    )


def _receipt(tmp_path: Path, task_id: str) -> dict[str, object]:
    return json.loads((tmp_path / task_id / "receipt.json").read_text(encoding="utf-8"))


def test_interrupted_cloud_lane_is_terminal_no_redispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sink = _Sink(tmp_path / "telegram.sqlite3")
    dispatcher = _Dispatcher(_lane(143, "interrupted"))

    second = _cloud_attempt(tmp_path, monkeypatch, sink, dispatcher)
    task_id = second.task_id

    assert second.status == "blocked"
    stored = PersonalStore(tmp_path).get(task_id)
    assert stored is not None and stored.status == "blocked"
    receipt = _receipt(tmp_path, task_id)
    assert receipt["status"] == "blocked"
    assert "interrupted" in str(receipt["error"])
    assert "no automatic re-dispatch" in str(receipt["error"])
    assert len(dispatcher.calls) == 1
    # A terminal row is never picked again: a third poll is a no-op.
    assert (
        poll_personal_tasks(
            tmp_path, sink, _Caller(), dispatcher=dispatcher, recall=lambda query: ""
        )
        is None
    )
    assert len(dispatcher.calls) == 1


def test_sigterm_killed_lane_exit_code_is_terminal_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sink = _Sink(tmp_path / "telegram.sqlite3")
    dispatcher = _Dispatcher(_lane(-15, "failed"))

    second = _cloud_attempt(tmp_path, monkeypatch, sink, dispatcher)

    assert second.status == "blocked"
    receipt = _receipt(tmp_path, second.task_id)
    assert "no automatic re-dispatch" in str(receipt["error"])
    assert len(dispatcher.calls) == 1


def test_cloud_attempt_cap_defaults_to_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from portal.modules.orchestration import personal_runner

    assert personal_runner._personal_cloud_cap() == 1
    sink = _Sink(tmp_path / "telegram.sqlite3")
    dispatcher = _Dispatcher(_lane(1, "failed"))

    second = _cloud_attempt(tmp_path, monkeypatch, sink, dispatcher)

    assert second.status == "blocked"
    assert len(dispatcher.calls) == 1
    receipt = _receipt(tmp_path, second.task_id)
    assert "cap 1" in str(receipt["error"])
    stored = PersonalStore(tmp_path).get(second.task_id)
    assert stored is not None and stored.status == "blocked"


def test_configured_cap_retries_then_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portal.modules.orchestration import personal_runner

    monkeypatch.setattr(personal_runner, "_personal_cloud_cap", lambda: 3, raising=False)
    sink = _Sink(tmp_path / "telegram.sqlite3")
    dispatcher = _Dispatcher(_lane(1, "failed"))

    second = _cloud_attempt(tmp_path, monkeypatch, sink, dispatcher)
    assert second.status == "cloud-retry"
    assert len(dispatcher.calls) == 1
    stored = PersonalStore(tmp_path).get(second.task_id)
    assert stored is not None and stored.status == "cloud_retry"

    third = poll_personal_tasks(
        tmp_path, sink, _Caller(), dispatcher=dispatcher, recall=lambda query: ""
    )
    assert third is not None and third.status == "cloud-retry"

    fourth = poll_personal_tasks(
        tmp_path, sink, _Caller(), dispatcher=dispatcher, recall=lambda query: ""
    )

    assert fourth is not None and fourth.status == "blocked"
    assert len(dispatcher.calls) == 3
    assert dispatcher.calls[0]["tier"] == "auto"
    assert dispatcher.calls[2]["tier"] == "escalate"
    receipt = _receipt(tmp_path, second.task_id)
    assert "cap 3" in str(receipt["error"])
    stored = PersonalStore(tmp_path).get(second.task_id)
    assert stored is not None and stored.status == "blocked"


def test_operator_cancel_stops_a_running_cloud_lane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store_path = tmp_path / "arm.sqlite3"
    monkeypatch.setenv("PORTAL_ARM_TELEGRAM_DB", str(store_path))

    holder: dict[str, str] = {}

    class CancelledLane:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def run(self, **kwargs: object) -> SimpleNamespace:
            self.calls.append(kwargs)
            check = kwargs["cancel_check"]
            assert callable(check) and check() is False
            ArmTelegramStore(store_path).add_control_request(
                1, "cancel", holder["task_id"], status="queued"
            )
            assert callable(check) and check() is True
            return _lane(-15, "failed")

    dispatcher = CancelledLane()
    sink = _Sink(tmp_path / "telegram.sqlite3")
    telegram_do_reply(tmp_path, 7, "help with an invalid local plan")
    runnable = PersonalStore(tmp_path).oldest_runnable()
    assert runnable is not None
    holder["task_id"] = runnable.id

    from portal.modules.orchestration import personal_runner

    monkeypatch.setattr(personal_runner, "_personal_cloud_enabled", lambda: True, raising=False)
    first = poll_personal_tasks(tmp_path, sink, _Caller(), recall=lambda query: "")
    assert first is not None and first.status == "retrying"
    second = poll_personal_tasks(
        tmp_path, sink, _Caller(), dispatcher=dispatcher, recall=lambda query: ""
    )

    assert second is not None and second.status == "cancelled"
    stored = PersonalStore(tmp_path).get(second.task_id)
    assert stored is not None and stored.status == "cancelled"
    receipt = _receipt(tmp_path, second.task_id)
    assert receipt["status"] == "cancelled"
    assert "cancelled by operator" in str(receipt["error"])
    assert len(dispatcher.calls) == 1
    assert (
        poll_personal_tasks(
            tmp_path, sink, _Caller(), dispatcher=dispatcher, recall=lambda query: ""
        )
        is None
    )


def test_cancel_check_is_always_offered_to_the_dispatcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ProbeLane:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []
            self.seen: bool | None = None

        def run(self, **kwargs: object) -> SimpleNamespace:
            self.calls.append(kwargs)
            check = kwargs["cancel_check"]
            assert callable(check)
            self.seen = bool(check())
            return _lane(1, "failed")

    probe = ProbeLane()
    sink = _Sink(tmp_path / "telegram.sqlite3")

    _cloud_attempt(tmp_path, monkeypatch, sink, probe)

    assert len(probe.calls) == 1
    assert probe.seen is False


def test_personal_cancel_queued_reads_only_confirmed_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PORTAL_ARM_TELEGRAM_DB", str(tmp_path / "arm.sqlite3"))
    store = ArmTelegramStore(tmp_path / "arm.sqlite3")

    assert control.personal_cancel_queued("pt-1") is False
    store.add_control_request(1, "cancel", "pt-1", status="pending")
    assert control.personal_cancel_queued("pt-1") is False
    store.add_control_request(1, "cancel", "pt-1", status="queued")
    assert control.personal_cancel_queued("pt-1") is True
    assert control.personal_cancel_queued("pt-2") is False


def test_cancel_job_routes_personal_task_ids(tmp_path: Path) -> None:
    store = PersonalStore(tmp_path)
    task = store.add("telegram", "7", "status please")

    assert (
        control.cancel_job(tmp_path, task.id, "cancelled from Telegram") == f"cancelled {task.id}"
    )
    stored = store.get(task.id)
    assert stored is not None and stored.status == "cancelled"
    assert control.cancel_job(tmp_path, task.id, "again") == f"{task.id} is already cancelled"

    stranger = store.add("telegram", "7", "another")
    stranger_id = stranger.id
    store.update(stranger_id, status="done", expect=frozenset({"queued"}))
    assert control.cancel_job(tmp_path, stranger_id, "again") == f"{stranger_id} is already done"

    with pytest.raises(ValueError, match="no queue task"):
        control.cancel_job(tmp_path, "pt-missing", "again")


def test_dispatch_wait_process_stops_the_lane_on_cancel() -> None:
    from portal.modules.orchestration.escalate import _wait_process

    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True
    )
    try:
        code = _wait_process(proc, 60.0, 0.01, lambda _s: None, cancel_check=lambda: True)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert code == -15


# ── the poll-based handoff (2026-11-20: the lane result never came back) ───────


RESULT_BLOCK = (
    "## RESULT\n"
    "done — the request is answered from live read-only observation.\n\n"
    "Pipeline :9099 OK, 12/12 backends healthy; Ollama loaded exactly one model."
)


class _AsyncDispatcher:
    """The real start/outcome/alive/result shape, with no process and no registry."""

    def __init__(
        self,
        *,
        block: str = RESULT_BLOCK,
        finished: bool = False,
        alive: bool = True,
        exit_code: int = 0,
        status: str = "completed",
    ) -> None:
        self.block = block
        self.finished = finished
        self.alive_now = alive
        self.exit_code = exit_code
        self.run_status = status
        self.starts: list[dict[str, object]] = []
        self.paths: list[Path] = []

    def start(self, **kwargs: object) -> SimpleNamespace:
        self.starts.append(kwargs)
        path = Path(str(kwargs["log_path"]))
        self.paths.append(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("dispatch output\n", encoding="utf-8")
        return SimpleNamespace(pid=0, runs_before=0, log_path=path)

    def finish(self) -> None:
        self.finished = True

    def outcome(self, *, role: str, repo: Path, runs_before: int = 0) -> dict[str, object] | None:
        if not self.finished:
            return None
        return {"exit": self.exit_code, "status": self.run_status, "model": "mock-model"}

    def alive(self, *, role: str) -> bool:
        return self.alive_now

    def result(self, *, role: str, repo: Path) -> str:
        return self.block


def _handed_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dispatcher: _AsyncDispatcher
) -> tuple[Path, str, _Sink]:
    from portal.modules.orchestration import personal_runner

    monkeypatch.setattr(personal_runner, "_personal_cloud_enabled", lambda: True, raising=False)
    sink = _Sink(tmp_path / "telegram.sqlite3")
    telegram_do_reply(tmp_path, 7, "what is the Portal pipeline status")
    first = poll_personal_tasks(tmp_path, sink, _Caller(), recall=lambda _q: "")
    assert first is not None and first.status == "retrying"
    run = poll_personal_tasks(
        tmp_path, sink, _Caller(), dispatcher=dispatcher, recall=lambda _q: ""
    )
    assert run is not None and run.status == "cloud-running"
    assert dispatcher.starts, "the lane was started"
    return tmp_path, run.task_id, sink


def test_a_slow_cloud_lane_does_not_stall_the_tasks_behind_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatcher = _AsyncDispatcher()
    tasks, task_id, sink = _handed_off(tmp_path, monkeypatch, dispatcher)

    # The lane is still running: the queue must pick up the next task in the same poll.
    telegram_do_reply(tasks, 7, "what is the queue status in one paragraph")
    caller = _PlanCaller(
        [
            Completion('{"steps": [{"id":"s1","tools":["queue_status"]}]}', (), 0),
            Completion("Queue is empty.", (), 1, ("queue_status",)),
        ]
    )
    queued = poll_personal_tasks(tasks, sink, caller, dispatcher=dispatcher, recall=lambda _q: "")

    assert queued is not None
    assert queued.task_id != task_id, "the task behind the lane ran while it was in flight"
    assert queued.status == "done"
    stored = PersonalStore(tasks).get(task_id)
    assert stored is not None and stored.status == "cloud-running"
    assert len(dispatcher.starts) == 1, "the in-flight lane was not dispatched twice"


def test_a_finished_cloud_lane_delivers_its_result_to_the_task_and_the_operator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatcher = _AsyncDispatcher()
    tasks, task_id, sink = _handed_off(tmp_path, monkeypatch, dispatcher)

    dispatcher.finish()
    collected = poll_personal_tasks(tasks, sink, _Caller(), dispatcher=dispatcher)

    assert collected is not None and collected.status == "done"
    stored = PersonalStore(tasks).get(task_id)
    assert stored is not None and stored.status == "done"
    receipt = _receipt(tasks, task_id)
    assert receipt["status"] == "done"
    assert "12/12 backends healthy" in str(receipt["final_text"])
    assert any("12/12 backends healthy" in message for message in sink.messages)


def test_a_lane_that_died_without_a_record_is_reported_not_waited_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatcher = _AsyncDispatcher(alive=False)
    tasks, task_id, sink = _handed_off(tmp_path, monkeypatch, dispatcher)
    record_path = tasks / task_id / "attempts" / "cloud-1" / "receipt.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["started"] = 0
    record_path.write_text(json.dumps(record), encoding="utf-8")
    stale = record_path.stat().st_mtime - 10_000
    os.utime(record_path, (stale, stale))

    collected = poll_personal_tasks(tasks, sink, _Caller(), dispatcher=dispatcher)

    assert collected is not None and collected.status == "blocked"
    receipt = _receipt(tasks, task_id)
    assert "no run record" in str(receipt["error"]) or "run record" in str(receipt["error"])
    assert any("run record" in message for message in sink.messages)


def test_a_cloud_lane_that_returns_no_result_blocks_honestly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatcher = _AsyncDispatcher(block="")
    tasks, task_id, sink = _handed_off(tmp_path, monkeypatch, dispatcher)

    dispatcher.finish()
    collected = poll_personal_tasks(tasks, sink, _Caller(), dispatcher=dispatcher)

    assert collected is not None and collected.status == "blocked"
    receipt = _receipt(tasks, task_id)
    assert "## RESULT" in str(receipt["final_text"])
    assert "without a ## RESULT block" in str(receipt["error"])


def test_the_handoff_receipt_records_the_lane_and_its_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatcher = _AsyncDispatcher()
    tasks, task_id, _sink = _handed_off(tmp_path, monkeypatch, dispatcher)

    record = json.loads(
        (tasks / task_id / "attempts" / "cloud-1" / "receipt.json").read_text(encoding="utf-8")
    )
    start = dispatcher.starts[0]
    assert record["role"] == start["role"]
    assert record["role"] == f"jarvis-personal-{task_id}-a1"
    assert record["runs_before"] == 0
    assert Path(str(start["log_path"])).parent.name == "cloud-1"


def test_cancel_signals_a_running_cloud_lane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portal.modules.orchestration.personal_runner import cancel_personal_task

    dispatcher = _AsyncDispatcher()
    tasks, task_id, _sink = _handed_off(tmp_path, monkeypatch, dispatcher)
    role = f"jarvis-personal-{task_id}-a1"
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)", role], start_new_session=True
    )
    try:
        record_path = tasks / task_id / "attempts" / "cloud-1" / "receipt.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["pid"] = proc.pid
        record_path.write_text(json.dumps(record), encoding="utf-8")

        reply = cancel_personal_task(tasks, task_id)

        assert reply == f"cancelled {task_id} (cloud lane signalled)"
        proc.wait(timeout=10)
        assert proc.returncode is not None
    finally:
        if proc.poll() is None:
            proc.kill()
    assert PersonalStore(tasks).get(task_id).status == "cancelled"


def test_escalation_kind_follows_the_request() -> None:
    from portal.modules.orchestration.escalate import personal_dispatch_kind

    status = "what is the Portal pipeline status and which models are loaded right now"
    review = "review scripts/engine_install_plan.py and report every code path"
    action = "snapshot the throwaway VM"
    security = "run the security sweep and fix the critical detections"
    assert personal_dispatch_kind(status) == "research"
    assert personal_dispatch_kind(review) == "review"
    assert personal_dispatch_kind(action) == "code"
    assert personal_dispatch_kind(security) == "security"


_FAKE_DISPATCH = """
import json, sys
from pathlib import Path

args = sys.argv[1:]
if args and args[0] == "status":
    print("status: no running lanes")
    sys.exit(0)
repo = Path(args[args.index("--repo") + 1])
if "result" in args:
    print("## RESULT\\ndone - answered from the fake lane.")
    sys.exit(0)
role = args[args.index("--role") + 1]
worktree = repo.parent / f"{repo.name}-{role}"
registry = Path(__file__).resolve().parent.parent / "registry.json"
data = json.loads(registry.read_text()) if registry.exists() else {"roles": {}}
entry = data.setdefault("roles", {}).setdefault(
    f"{worktree}::{role}", {"role": role, "runs": []}
)
entry["runs"].append({"exit": 0, "status": "completed", "model": "fake-model"})
registry.write_text(json.dumps(data))
"""


def test_the_process_dispatcher_starts_a_lane_and_collects_it(tmp_path: Path) -> None:
    """start/outcome/result against a stand-in dispatch.py: no live lane, no network."""
    import time

    from portal.modules.orchestration.escalate import ProcessDispatcher

    binary = tmp_path / "orchestrate" / "bin" / "dispatch.py"
    binary.parent.mkdir(parents=True)
    binary.write_text(_FAKE_DISPATCH, encoding="utf-8")
    repo = tmp_path / "portal-5" / "proj"
    repo.mkdir(parents=True)
    brief = tmp_path / "brief.md"
    brief.write_text("do the thing", encoding="utf-8")
    role = "jarvis-personal-pt-1-a1"
    dispatcher = ProcessDispatcher(binary, timeout_s=30, poll_s=0.01)

    started = dispatcher.start(
        role=role,
        tier="auto",
        kind="research",
        brief=brief,
        repo=repo,
        log_path=tmp_path / "cloud-1" / "dispatch.log",
    )
    assert started.role == role and started.runs_before == 0

    record = None
    for _ in range(100):
        record = dispatcher.outcome(role=role, repo=repo, runs_before=started.runs_before)
        if record is not None:
            break
        time.sleep(0.05)

    assert record is not None and record["exit"] == 0 and record["model"] == "fake-model"
    assert dispatcher.result(role=role, repo=repo).startswith("## RESULT")
    assert dispatcher.alive(role=role) is False
