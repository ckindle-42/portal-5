"""Personal tool loop and planner. No network."""

from __future__ import annotations

import json
import time
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
from portal.modules.orchestration.personal_runner import (
    Completion,
    apply_personal_decision,
    poll_personal_tasks,
)
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
        self.recall_bodies: list[dict[str, Any]] = []
        self.recall_reply = Completion("No matching operator memory.", (), 1, ("recall",))

    def complete(self, body: dict[str, Any]) -> Completion:
        saved = json.loads(json.dumps(body))
        if body.get("portal_bite_tools") == ["recall"]:
            self.recall_bodies.append(saved)
            return self.recall_reply
        self.bodies.append(saved)
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
    result = poll_personal_tasks(tmp_path, _Notices(), caller)
    receipt_path = next((tmp_path).glob("*/receipt.json"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    # Hop-cap exhaustion without a final answer is now a retryable J9 failure.
    assert result is not None and result.status == "retrying"
    assert receipt["hops"] <= HOP_CAP
    assert receipt["tool_calls"].count("queue_status") <= 2


def test_tool_outside_the_allowlist_is_not_logged(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 1, "run the mystery command")
    caller = _Caller([Completion(_plan("shell_exec"), (), 0), Completion("should not run", (), 0)])
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


def test_read_only_plan_without_budget_defaults_and_runs_from_receipt_shape(tmp_path: Path) -> None:
    """pt-335077e03d03 regression: real planner omitting optional budget/paths must validate and run."""
    reply = telegram_do_reply(tmp_path, 5388311056, "what is the queue status in one paragraph")
    task_id = reply.removeprefix("queued ")
    plan_without_budget = json.dumps({"steps": [{"id": "step-0", "tools": ["queue_status"]}]})
    caller = _Caller(
        [
            Completion(plan_without_budget, (), 0),
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
            Completion("Queue has 0 queued and 0 running jobs.", (), 0),
        ]
    )
    notices = _Notices()
    result = poll_personal_tasks(tmp_path, notices, caller)
    assert result is not None and result.status == "done"
    receipt = json.loads((tmp_path / task_id / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["error"] == ""
    assert receipt["workspace"] == FAST_WORKSPACE
    assert receipt["tool_calls"] == ["queue_status"]
    assert receipt["plan"]["steps"][0]["budget"]["context_tokens"] > 0
    assert receipt["plan"]["steps"][0]["paths"] == []
    assert notices.messages == [(task_id, "personal", "Queue has 0 queued and 0 running jobs.")]


def test_genuinely_invalid_plan_blocks_after_two_attempts_without_cloud(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portal.modules.orchestration import personal_runner

    monkeypatch.setattr(personal_runner, "_personal_cloud_enabled", lambda: False)
    reply = telegram_do_reply(tmp_path, 5388311056, "what is the queue status in one paragraph")
    task_id = reply.removeprefix("queued ")
    caller = _Caller([Completion("not json at all", (), 0), Completion("still not json", (), 0)])
    notices = _Notices()
    first = poll_personal_tasks(tmp_path, notices, caller)
    result = poll_personal_tasks(tmp_path, notices, caller)
    assert first is not None and first.status == "retrying"
    assert result is not None and result.status == "blocked"
    receipt = json.loads((tmp_path / task_id / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["plan"] is None
    assert receipt["status"] == "blocked"
    assert len(receipt["local_attempts"]) == 2
    assert receipt["hops"] == 1
    assert receipt["error"]
    assert notices.messages[-1][0] == task_id
    assert receipt["error"] in notices.messages[-1][2]


def test_validator_rejects_bad_budget_types_and_bounds(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="budget"):
        validate_personal_plan(
            {"steps": [{"tools": ["queue_status"], "budget": "invalid"}]},
            tmp_path,
            frozenset(),
        )
    with pytest.raises(ValueError, match="exceeds"):
        validate_personal_plan(
            {"steps": [{"tools": ["queue_status"], "budget": {"context_tokens": 999_999}}]},
            tmp_path,
            frozenset(),
        )


def test_telegram_notice_sink_exposes_notify_for_personal_tasks(tmp_path: Path) -> None:
    from portal.modules.orchestration.telegram import TelegramNoticeSink

    sink = TelegramNoticeSink(path=tmp_path / "arm.sqlite3")
    sink.notify("pt-123", "personal", "hello")
    assert any(row.message == "hello" for row in sink.store.outbox())


def test_long_personal_task_sends_one_checkin_before_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portal.modules.orchestration import personal_runner

    monkeypatch.setattr(personal_runner, "PERSONAL_CHECKIN_SECONDS", 0.5, raising=False)

    class SlowCaller(_Caller):
        def complete(self, body: dict[str, Any]) -> Completion:
            if len(self.bodies) == 2:
                time.sleep(0.75)
            return super().complete(body)

    reply = telegram_do_reply(tmp_path, 1, "read the newest arm receipt")
    task_id = reply.removeprefix("queued ")
    caller = SlowCaller(
        [
            Completion(_plan("read_receipt"), (), 0),
            Completion(
                "",
                (
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "read_receipt", "arguments": "{}"},
                    },
                ),
                0,
            ),
            Completion("Receipt read.", (), 0),
        ]
    )
    notices = _Notices()

    result = poll_personal_tasks(tmp_path, notices, caller)

    assert result is not None and result.status == "done"
    assert len(notices.messages) == 2
    checkin = notices.messages[0][2]
    last_tool = checkin.split("last tool: ", 1)[1]
    assert task_id in checkin and "hop" in checkin
    assert last_tool in {"recall", "read_receipt"}
    assert notices.messages[1][2] == "Receipt read."


def test_confirmed_template_request_hands_to_arm_and_rejects_external_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portal.modules.orchestration import owui_entry
    from portal.modules.orchestration.queue import QueueLedger

    repo = Path.cwd()
    queue_root = tmp_path
    monkeypatch.setattr(owui_entry, "tasks_root", lambda: queue_root)
    monkeypatch.setattr(owui_entry, "_allow_roots", lambda: (repo, tmp_path))
    action = {
        "action": "enqueue-template",
        "discipline": "test_fixing",
        "template_key": "repair_with_tests",
        "parameters": {
            "source_file": "portal/modules/orchestration/personal_runner.py",
            "test_file": "tests/unit/test_jarvis_personal_loop.py",
            "expected_behavior": "preserve the planned behavior",
        },
    }
    telegram_do_reply(tmp_path, 1, "queue a test_fixing repair")
    caller = _Caller([Completion(json.dumps(action), (), 0)])
    sink = _Notices()

    pending = poll_personal_tasks(tmp_path, sink, caller)
    assert pending is not None and pending.status == "pending"
    assert apply_personal_decision(tmp_path, pending.task_id, "confirm") == "confirmed"
    handed = poll_personal_tasks(tmp_path, sink, caller)

    assert handed is not None and handed.status == "handed-to-arm"
    receipt = json.loads((tmp_path / pending.task_id / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["arm_task_id"] == f"jarvis-{pending.task_id}"
    with QueueLedger(queue_root) as ledger:
        assert len(ledger.items()) == 1

    queue_root = tmp_path / "bad"
    telegram_do_reply(queue_root, 1, "queue a test_fixing repair")
    action["parameters"] = {
        "source_file": "/etc/passwd",
        "test_file": "tests/unit/test_jarvis_personal_loop.py",
        "expected_behavior": "preserve the planned behavior",
    }
    bad_caller = _Caller([Completion(json.dumps(action), (), 0)])
    rejected = poll_personal_tasks(queue_root, sink, bad_caller)
    assert rejected is not None and rejected.status == "rejected"
    with QueueLedger(queue_root) as ledger:
        assert ledger.items() == []


# ── J9 acceptance check ────────────────────────────────────────────────────────


def test_acceptance_check_flags_the_three_real_failures() -> None:
    from portal.modules.orchestration.personal_policy import acceptance_failure

    plan = {"steps": [{"id": "s0", "tools": ["queue_status"], "paths": [], "budget": {}}]}
    satisfied = acceptance_failure(plan, "Two jobs queued.", ["queue_status"], [])
    assert satisfied is None
    assert acceptance_failure(plan, "   ", [], []) is not None
    tool_error = acceptance_failure(
        plan, "Done.", ["queue_status"], ['{"error": "Tool \'x\' in backoff"}']
    )
    assert tool_error is not None and "tool error" in tool_error
    unsatisfied = acceptance_failure(plan, "I could not check.", [], [])
    assert unsatisfied is not None and "not satisfied" in unsatisfied
    clean_output = acceptance_failure(plan, "Ok.", ["queue_status"], ['{"counts": {}}'])
    assert clean_output is None


def test_empty_answer_is_a_retryable_failure_that_reaches_cloud_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A completed-but-empty local attempt counts as a real J9 failure."""
    from types import SimpleNamespace

    from portal.modules.orchestration import personal_runner

    class Dispatcher:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def run(self, **kwargs: object) -> SimpleNamespace:
            self.calls.append(kwargs)
            return SimpleNamespace(
                exit_code=0, status="complete", model="mock", result_text="Cloud lane ran."
            )

    telegram_do_reply(tmp_path, 1, "what is the queue status in one paragraph")
    task_id = PersonalStore(tmp_path).oldest_runnable()
    assert task_id is not None
    caller = _Caller(
        [
            Completion(_plan("queue_status"), (), 0),
            Completion("", (), 0),
            Completion(_plan("queue_status"), (), 0),
            Completion("", (), 0),
        ]
    )
    notices = _Notices()
    dispatcher = Dispatcher()
    monkeypatch.setattr(personal_runner, "_personal_cloud_enabled", lambda: True, raising=False)

    first = poll_personal_tasks(tmp_path, notices, caller)
    second = poll_personal_tasks(tmp_path, notices, caller, dispatcher=dispatcher)

    assert first is not None and first.status == "retrying"
    assert second is not None and second.status == "handed-to-cloud"
    attempt = json.loads(
        (tmp_path / task_id.id / "attempts" / "local-1" / "receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert attempt["error"] == "acceptance: empty final answer"
    receipt = json.loads((tmp_path / task_id.id / "receipt.json").read_text(encoding="utf-8"))
    assert len(receipt["local_attempts"]) == 2
    brief = Path(str(dispatcher.calls[0]["brief"]))
    assert "acceptance: empty final answer" in brief.read_text(encoding="utf-8")


def test_a_dispatched_tool_error_is_a_retryable_failure(tmp_path: Path) -> None:
    """J9: a tool that answered with an error object is a failed attempt."""
    telegram_do_reply(tmp_path, 1, "summarize the repository state")
    caller = _Caller(
        [
            Completion(_plan("git_status"), (), 0),
            Completion(
                "I could not read the repository.",
                (),
                1,
                ("git_status",),
                ('{"error": "Tool \'git_status\' not in registry — call ignored"}',),
            ),
        ]
    )
    result = poll_personal_tasks(tmp_path, _Notices(), caller)
    assert result is not None and result.status == "retrying"
    receipt = json.loads(next(tmp_path.glob("*/receipt.json")).read_text(encoding="utf-8"))
    assert "acceptance: tool error" in receipt["error"]
