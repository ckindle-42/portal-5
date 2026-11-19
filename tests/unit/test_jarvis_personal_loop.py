"""J3: one Pipeline tool loop, hop cap 8, receipt and outbox. No network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from portal.modules.orchestration.personal_intake import telegram_do_reply
from portal.modules.orchestration.personal_policy import FAST_WORKSPACE, HOP_CAP
from portal.modules.orchestration.personal_runner import Completion, poll_personal_tasks
from portal.modules.orchestration.personal_store import PersonalStore


class _Notices:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    def notify(self, task_id: str, kind: str, message: str) -> None:
        self.messages.append((task_id, kind, message))


class _Caller:
    def __init__(self, replies: list[Completion]) -> None:
        self.replies = list(replies)
        self.bodies: list[dict[str, Any]] = []

    def complete(self, body: dict[str, Any]) -> Completion:
        self.bodies.append(body)
        return self.replies.pop(0)


def test_tool_loop_writes_receipt_and_outbox_within_eight_hops(tmp_path: Path) -> None:
    reply = telegram_do_reply(tmp_path, 1, "what is the queue status in one paragraph")
    task_id = reply.removeprefix("queued ")
    caller = _Caller(
        [
            Completion(
                "",
                (
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "queue_status", "arguments": "{}"},
                    },
                ),
                0,
            ),
            Completion("queued 0, running 0.", (), 0),
        ]
    )
    notices = _Notices()
    result = poll_personal_tasks(tmp_path, notices, caller)
    assert result is not None and result.status == "done"
    task = PersonalStore(tmp_path).get(task_id)
    assert task is not None and task.status == "done"
    receipt = json.loads((tmp_path / task_id / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["workspace"] == FAST_WORKSPACE
    assert receipt["hops"] <= HOP_CAP
    assert receipt["tool_calls"] == ["queue_status"]
    assert "running 0" in receipt["final_text"]
    assert notices.messages == [(task_id, "personal", receipt["final_text"])]
    assert caller.bodies[0]["model"] == FAST_WORKSPACE
    assert caller.bodies[0]["portal_bite_max_hops"] <= HOP_CAP
    assert set(caller.bodies[0]["portal_bite_tools"]) <= {
        "recall",
        "wiki_search",
        "wiki_get_unit",
        "queue_status",
        "read_receipt",
    }


def test_ninth_local_hop_is_not_executed(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 1, "status please")
    calls = tuple(
        {
            "id": f"c{i}",
            "type": "function",
            "function": {"name": "queue_status", "arguments": "{}"},
        }
        for i in range(3)
    )
    caller = _Caller([Completion("", calls, 6), Completion("stopped", (), 0)])
    poll_personal_tasks(tmp_path, _Notices(), caller)
    receipt_path = next((tmp_path).glob("*/receipt.json"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["hops"] <= HOP_CAP
    assert len(receipt["tool_calls"]) <= 2


def test_tool_outside_the_allowlist_is_not_logged(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 1, "push the branch")
    caller = _Caller(
        [
            Completion(
                "",
                (
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "git_push", "arguments": "{}"},
                    },
                ),
                0,
            )
        ]
    )
    result = poll_personal_tasks(tmp_path, _Notices(), caller)
    assert result is not None and result.status == "rejected"
    task = PersonalStore(tmp_path).oldest_runnable()
    assert task is None
    stored = PersonalStore(tmp_path).get(result.task_id)
    assert stored is not None and stored.tool_log == "[]"
    assert json.loads(stored.tool_log) == []
