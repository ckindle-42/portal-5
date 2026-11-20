"""Personal tool loop and planner. No network."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from portal.modules.orchestration.personal_intake import telegram_do_reply
from portal.modules.orchestration.personal_policy import (
    HOP_CAP,
    PLANNER_WORKSPACE,
    validate_personal_plan,
)
from portal.modules.orchestration.personal_runner import (
    Completion,
    _memory_recall,
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

    def complete(self, body: dict[str, Any]) -> Completion:
        self.bodies.append(json.loads(json.dumps(body)))
        return self.replies.pop(0)


def _no_memory(query: str) -> str:
    return ""


@pytest.fixture(autouse=True)
def _offline_recall(monkeypatch: pytest.MonkeyPatch) -> None:
    """The memory MCP is never reached from a unit test."""
    from portal.modules.orchestration import personal_runner

    monkeypatch.setattr(personal_runner, "_memory_recall", _no_memory)


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        raise AssertionError("personal cloud dispatch must not run")


def _receipt(tmp_path: Path, task_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(
        (tmp_path / task_id / "receipt.json").read_text(encoding="utf-8")
    )
    return payload


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


# The mocked tool-loop happy path (plan → tool call → done → receipt shape) is
# exercised live by `portal trace --section jarvis`; the offline duplicate
# (test_tool_loop_writes_receipt_and_outbox_within_eight_hops,
# test_read_only_plan_without_budget_defaults_and_runs_from_receipt_shape,
# test_code_tools_wait_for_confirm) was paid for that hop and its negative.
# Confirm/safety/contract nets stay below.


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
    assert receipt["hops"] == 0  # recall is a direct MCP call, not a model hop
    assert receipt["error"]
    assert notices.messages[-1][0] == task_id
    assert receipt["error"] in notices.messages[-1][2]


def test_a_pipeline_tool_handed_back_to_the_runner_is_a_retryable_fault(tmp_path: Path) -> None:
    """The seat's MCP tools belong to the Pipeline; a call returned to us is a fault, not a denial."""
    telegram_do_reply(tmp_path, 1, "what is the Portal pipeline status")
    call = {
        "id": "c1",
        "type": "function",
        "function": {"name": "get_pipeline_status", "arguments": "{}"},
    }
    caller = _Caller([Completion(_plan("get_pipeline_status"), (), 0), Completion("", (call,), 0)])

    result = poll_personal_tasks(tmp_path, _Notices(), caller, recall=_no_memory)

    assert result is not None and result.status == "retrying"
    receipt = json.loads((tmp_path / result.task_id / "receipt.json").read_text(encoding="utf-8"))
    assert "instead of dispatching" in str(receipt["error"])


def test_an_ambiguous_request_asks_one_question_and_calls_no_tool(tmp_path: Path) -> None:
    """2026-11-20 scenario: "clean things up" must ask, never guess a destructive action."""
    from portal.modules.orchestration.personal_policy import concrete_work_question

    telegram_do_reply(tmp_path, 1, "clean things up")
    caller = _Caller([])
    notices = _Notices()

    result = poll_personal_tasks(tmp_path, notices, caller, recall=_no_memory)

    question = concrete_work_question("clean things up")
    assert result is not None and result.status == "done"
    assert caller.bodies == [], "the model is not asked to guess a cleanup"
    receipt = json.loads((tmp_path / result.task_id / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["final_text"] == question
    assert receipt["tool_calls"] == []
    assert notices.messages[-1][2] == question


def test_an_ask_plan_without_a_question_is_rejected(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 1, "what is the queue status")
    caller = _Caller(
        [Completion('{"action": "ask"}', (), 0), Completion('{"action": "ask"}', (), 0)]
    )

    result = poll_personal_tasks(tmp_path, _Notices(), caller, recall=_no_memory)

    assert result is not None and result.status == "retrying"
    receipt = json.loads((tmp_path / result.task_id / "receipt.json").read_text(encoding="utf-8"))
    assert "question" in str(receipt["error"])


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
    checkin_sent = threading.Event()

    class WaitingNotices(_Notices):
        def notify(self, task_id: str, kind: str, message: str) -> None:
            super().notify(task_id, kind, message)
            if message.startswith("Personal task check-in."):
                checkin_sent.set()

    class SlowCaller(_Caller):
        def complete(self, body: dict[str, Any]) -> Completion:
            if len(self.bodies) == 2:
                assert checkin_sent.wait(timeout=5)
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
    notices = WaitingNotices()

    result = poll_personal_tasks(tmp_path, notices, caller)

    assert result is not None and result.status == "done"
    assert len(notices.messages) == 2
    checkin = notices.messages[0][2]
    assert f"Task: {task_id}" in checkin
    assert "hop: " in checkin and "last tool: " in checkin
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


def test_recall_fault_is_logged_and_the_task_still_runs(tmp_path: Path) -> None:
    """pt-3a85541ac6af: local-failed at hops 0 because recall never dispatched."""
    reply = telegram_do_reply(
        tmp_path, 1, "List the three largest files in /workspace/generated and report their sizes."
    )
    task_id = reply.removeprefix("queued ")
    caller = _Caller(
        [
            Completion(_plan("queue_status"), (), 0),
            Completion("Three files.", (), 1, ("queue_status",)),
        ]
    )

    def broken_recall(query: str) -> str:
        raise RuntimeError("task memory recall did not dispatch exactly one recall tool")

    result = poll_personal_tasks(tmp_path, _Notices(), caller, recall=broken_recall)

    assert result is not None and result.status == "done"
    receipt = _receipt(tmp_path, task_id)
    assert receipt["status"] == "done"
    assert receipt["plan"] is not None
    assert "task memory recall did not dispatch exactly one recall tool" in receipt["recall_error"]
    assert caller.bodies[0]["model"] == PLANNER_WORKSPACE
    assert "Recalled memory" not in caller.bodies[0]["messages"][-1]["content"]


def test_recall_fault_alone_never_retries_or_escalates_to_cloud(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portal.modules.orchestration import personal_runner

    monkeypatch.setattr(personal_runner, "_personal_cloud_enabled", lambda: True)
    reply = telegram_do_reply(tmp_path, 1, "what is the queue status in one paragraph")
    task_id = reply.removeprefix("queued ")
    dispatcher = _RecordingDispatcher()
    caller = _Caller(
        [
            Completion(_plan("queue_status"), (), 0),
            Completion("Queue is empty.", (), 1, ("queue_status",)),
        ]
    )

    def unreachable(query: str) -> str:
        raise RuntimeError("memory MCP unreachable")

    first = poll_personal_tasks(
        tmp_path, _Notices(), caller, dispatcher=dispatcher, recall=unreachable
    )

    assert first is not None and first.status == "done"
    assert dispatcher.calls == []
    assert not (tmp_path / task_id / "attempts").exists()
    assert "memory MCP unreachable" in _receipt(tmp_path, task_id)["recall_error"]


def test_recalled_memory_reaches_the_planner(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 1, "what is the queue status in one paragraph")
    caller = _Caller(
        [
            Completion(_plan("queue_status"), (), 0),
            Completion("Queue is empty.", (), 1, ("queue_status",)),
        ]
    )

    poll_personal_tasks(
        tmp_path, _Notices(), caller, recall=lambda query: "operator prefers terse answers"
    )

    assert "operator prefers terse answers" in caller.bodies[0]["messages"][-1]["content"]


def test_memory_text_keeps_memory_lines_and_flags_a_contract_error() -> None:
    from portal.modules.orchestration.personal_runner import _memory_text

    assert (
        _memory_text({"memories": [{"text": "likes terse answers", "similarity": 0.9}]})
        == "- likes terse answers"
    )
    assert _memory_text({"num_results": 0, "memories": []}) == ""
    with pytest.raises(ValueError, match="recall"):
        _memory_text({"error": "embedding failed"})


def test_the_default_recall_calls_the_memory_mcp_tool_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    from portal.platform.inference import mcp_http

    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen["url"] = str(request.url)
        seen["method"] = payload["method"]
        seen["params"] = payload["params"]
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "structuredContent": {
                        "memories": [{"text": "prefers terse replies", "similarity": 0.9}]
                    }
                },
            },
        )

    mcp_http._SERVER_STATES.clear()
    mcp_http._SERVER_LOCKS.clear()
    monkeypatch.setenv("MCP_MEMORY_URL", "http://memory.test:8920/")
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    assert _memory_recall("operator id 7: preferences") == "- prefers terse replies"
    assert seen["url"] == "http://memory.test:8920/mcp"
    assert seen["method"] == "tools/call"
    assert seen["params"]["name"] == "recall"
    assert seen["params"]["arguments"] == {"query": "operator id 7: preferences", "top_k": 5}


def test_a_broken_recall_still_escalates_a_task_that_fails_on_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from portal.modules.orchestration import personal_runner

    class Dispatcher:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def run(self, **kwargs: Any) -> SimpleNamespace:
            self.calls.append(kwargs)
            return SimpleNamespace(
                exit_code=0,
                status="complete",
                model="mock",
                result_text="## RESULT\ndone — cloud lane ran.",
            )

    monkeypatch.setattr(personal_runner, "_personal_cloud_enabled", lambda: True)
    reply = telegram_do_reply(tmp_path, 1, "help with an invalid local plan")
    task_id = reply.removeprefix("queued ")
    caller = _Caller([Completion("not JSON", (), 0), Completion("still not JSON", (), 0)])
    dispatcher = Dispatcher()

    def unreachable(query: str) -> str:
        raise RuntimeError("memory MCP unreachable")

    first = poll_personal_tasks(tmp_path, _Notices(), caller, recall=unreachable)
    second = poll_personal_tasks(
        tmp_path, _Notices(), caller, dispatcher=dispatcher, recall=unreachable
    )

    assert first is not None and first.status == "retrying"
    # The lane's own ## RESULT comes back into the task: no "handed-to-cloud" dead end.
    assert second is not None and second.status == "done"
    assert len(dispatcher.calls) == 1
    local = json.loads(
        (tmp_path / task_id / "attempts" / "local-1" / "receipt.json").read_text(encoding="utf-8")
    )
    assert "memory MCP unreachable" in local["recall_error"]
    assert "planner" in local["error"] or "JSON" in local["error"]
    assert "cloud lane ran" in _receipt(tmp_path, task_id)["final_text"]


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
    listing = {"steps": [{"id": "s0", "tools": ["workspace_files"], "paths": [], "budget": {}}]}
    word = (
        "write a one-page Word document summarising tonight's security sweep: "
        "MAL count, critical count, and what is still open"
    )
    fabricated = acceptance_failure(
        listing,
        "I cannot fulfill the request. MAL Count: [Insert MAL Count]",
        ["workspace_files"],
        ['{"files": []}'],
        request=word,
    )
    assert fabricated == "acceptance: word document was not created"
    review = acceptance_failure(
        listing,
        "The file does not exist in the workspace.",
        ["workspace_files"],
        ['{"files": [{"path": "generated/music/a.wav", "size": 1}]}'],
        request="review scripts/engine_install_plan.py and report every code path",
    )
    assert review is not None and "scripts/engine_install_plan.py" in review
    omitted = acceptance_failure(
        listing,
        "music_a.wav is 5760078 bytes",
        ["workspace_files"],
        ['{"files": [{"path": "generated/tasks/a.db", "size": 159576064}]}'],
        request="List the three largest files in /workspace/generated and report their sizes.",
    )
    assert omitted is not None and "largest file size" in omitted


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
                exit_code=0,
                status="complete",
                model="mock",
                result_text="## RESULT\ndone — cloud lane ran.",
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

    first = poll_personal_tasks(tmp_path, notices, caller, recall=_no_memory)
    second = poll_personal_tasks(
        tmp_path, notices, caller, dispatcher=dispatcher, recall=_no_memory
    )

    assert first is not None and first.status == "retrying"
    assert second is not None and second.status == "done"
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
    result = poll_personal_tasks(tmp_path, _Notices(), caller, recall=_no_memory)
    assert result is not None and result.status == "retrying"
    receipt = json.loads(next(tmp_path.glob("*/receipt.json")).read_text(encoding="utf-8"))
    assert "acceptance: tool error" in receipt["error"]
