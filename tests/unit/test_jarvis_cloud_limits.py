"""Jarvis personal cloud dispatch: attempt cap, interrupted lanes, operator cancel.

No network: dispatcher fakes only, and the Telegram control store lives in tmp_path.
"""

from __future__ import annotations

import json
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
