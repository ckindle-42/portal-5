"""Personal tool loop and planner. No network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from portal.modules.orchestration.personal_intake import telegram_do_reply
from portal.modules.orchestration.personal_policy import (
    FAST_WORKSPACE,
    HOP_CAP,
    PLANNER_WORKSPACE,
    validate_personal_plan,
)
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
        self.bodies.append(json.loads(json.dumps(body)))
        return self.replies.pop(0)


def _plan(*tools: str) -> str:
    return json.dumps(
        {
            "steps": [
                {
                    "id": "step",
                    "tools": list(tools),
                    "paths": [],
                    "budget": {"context_tokens": 2048},
                }
            ]
        }
    )


def test_tool_loop_writes_receipt_and_outbox_within_eight_hops(tmp_path: Path) -> None:
    reply = telegram_do_reply(tmp_path, 1, "what is the queue status in one paragraph")
    task_id = reply.removeprefix("queued ")
    caller = _Caller(
        [
            Completion(_plan("queue_status"), (), 0),
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
    assert caller.bodies[0]["model"] == PLANNER_WORKSPACE
    assert caller.bodies[0]["portal_no_tools"] is True
    assert caller.bodies[0]["tool_choice"] == "none"
    assert caller.bodies[1]["model"] == FAST_WORKSPACE
    assert caller.bodies[1]["portal_bite_max_hops"] <= HOP_CAP
    assert caller.bodies[1]["portal_bite_tools"] == ["queue_status"]
    assert "what is the queue" not in caller.bodies[1]["messages"][-1]["content"]
    assert "queue_status" in caller.bodies[1]["messages"][-1]["content"]


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
    caller = _Caller(
        [
            Completion(_plan("queue_status"), (), 0),
            Completion("", calls, 6),
            Completion("stopped", (), 0),
        ]
    )
    poll_personal_tasks(tmp_path, _Notices(), caller)
    receipt_path = next((tmp_path).glob("*/receipt.json"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["hops"] <= HOP_CAP
    assert len(receipt["tool_calls"]) <= 2


def test_tool_outside_the_allowlist_is_not_logged(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 1, "push the branch")
    caller = _Caller([Completion(_plan("git_push"), (), 0), Completion("should not run", (), 0)])
    result = poll_personal_tasks(tmp_path, _Notices(), caller)
    assert result is not None and result.status == "rejected"
    assert len(caller.bodies) == 1
    assert caller.bodies[0]["model"] == PLANNER_WORKSPACE
    stored = PersonalStore(tmp_path).get(result.task_id)
    assert stored is not None and stored.tool_log == "[]"
    assert stored.status == "rejected"


def test_code_tools_wait_for_confirm(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 1, "run the snippet")
    caller = _Caller([Completion(_plan("execute_python"), (), 0), Completion("printed 1", (), 0)])
    result = poll_personal_tasks(tmp_path, _Notices(), caller)
    assert result is not None and result.status == "pending"
    assert len(caller.bodies) == 1
    stored = PersonalStore(tmp_path).get(result.task_id)
    assert stored is not None and stored.tool_log == "[]"
    assert json.loads(stored.plan_json or "{}")["steps"][0]["tools"] == ["execute_python"]


def test_validator_rejects_mixed_steps_and_invented_paths(tmp_path: Path) -> None:
    mixed = {
        "steps": [
            {
                "tools": ["queue_status", "execute_bash"],
                "paths": [],
                "budget": {"context_tokens": 128},
            }
        ]
    }
    with pytest.raises(ValueError, match="separate"):
        validate_personal_plan(mixed, tmp_path, frozenset())
    invented = {
        "steps": [
            {
                "tools": ["read_receipt"],
                "paths": ["/etc/passwd"],
                "budget": {"context_tokens": 128},
            }
        ]
    }
    with pytest.raises(ValueError, match="outside"):
        validate_personal_plan(invented, tmp_path, frozenset())
