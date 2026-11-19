"""J5: risky personal steps wait for confirm and do not call tools. No network."""

from __future__ import annotations

import json
from pathlib import Path

from portal.modules.orchestration.personal_intake import telegram_do_reply
from portal.modules.orchestration.personal_policy import HELD_TEXT
from portal.modules.orchestration.personal_runner import (
    Completion,
    apply_personal_decision,
    poll_personal_tasks,
)
from portal.modules.orchestration.personal_store import PersonalStore
from portal_channels.telegram.arm_bridge import ArmTelegramStore


class _Caller:
    def __init__(self, replies: list[Completion]) -> None:
        self.replies = list(replies)
        self.bodies: list[dict[str, object]] = []

    def complete(self, body: dict[str, object]) -> Completion:
        self.bodies.append(json.loads(json.dumps(body)))
        if not self.replies:
            raise AssertionError("tool seat was called")
        return self.replies.pop(0)


class _Sink:
    def __init__(self, path: Path) -> None:
        self.store = ArmTelegramStore(path)
        self.messages: list[str] = []

    def notify(self, task_id: str, kind: str, message: str) -> None:
        self.messages.append(message)


def _plan(tool: str) -> str:
    return json.dumps(
        {"steps": [{"id": "step", "tools": [tool], "paths": [], "budget": {"context_tokens": 512}}]}
    )


def test_restart_is_pending_and_abort_cancels(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 7, "restart the pipeline")
    caller = _Caller([Completion(_plan("queue_status"), (), 0)])
    sink = _Sink(tmp_path / "telegram.sqlite3")
    result = poll_personal_tasks(tmp_path, sink, caller)
    assert result is not None and result.status == "pending"
    assert len(caller.bodies) == 1
    assert caller.bodies[0]["portal_no_tools"] is True
    task = PersonalStore(tmp_path).get(result.task_id)
    assert task is not None and task.status == "pending" and task.tool_log == "[]"
    pending = sink.store.pending_control_requests(result.task_id)
    assert [row.verb for row in pending] == ["personal"]
    assert apply_personal_decision(tmp_path, result.task_id, "abort") == "cancelled"
    assert PersonalStore(tmp_path).get(result.task_id).status == "cancelled"  # type: ignore[union-attr]


def test_confirm_holds_without_a_tool_call(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 7, "restart the pipeline")
    caller = _Caller([Completion(_plan("execute_bash"), (), 0)])
    sink = _Sink(tmp_path / "telegram.sqlite3")
    result = poll_personal_tasks(tmp_path, sink, caller)
    assert result is not None
    assert apply_personal_decision(tmp_path, result.task_id, "confirm") == "confirmed"
    held = poll_personal_tasks(tmp_path, sink, caller)
    assert held is not None and held.status == "held"
    receipt = json.loads((tmp_path / result.task_id / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["final_text"] == HELD_TEXT
    assert receipt["tool_calls"] == []
    assert receipt["hops"] == 0
    assert len(caller.bodies) == 1


def test_hidden_fleet_is_rejected_before_the_planner(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 7, "check proxmox for the vm")
    caller = _Caller([])
    result = poll_personal_tasks(tmp_path, _Sink(tmp_path / "telegram.sqlite3"), caller)
    assert result is not None and result.status == "rejected"
    assert caller.bodies == []
    stored = PersonalStore(tmp_path).get(result.task_id)
    assert stored is not None and stored.tool_log == "[]"
