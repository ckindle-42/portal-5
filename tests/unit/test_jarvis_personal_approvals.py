"""J5: risky personal requests wait for confirm and call no tool first. No network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from portal.modules.orchestration.personal_intake import telegram_do_reply
from portal.modules.orchestration.personal_policy import CODE_WORKSPACE, HELD_TEXT, text_gate
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


@pytest.fixture(autouse=True)
def _offline_recall(monkeypatch: pytest.MonkeyPatch) -> None:
    """The memory MCP is never reached from a unit test."""
    from portal.modules.orchestration import personal_runner

    monkeypatch.setattr(personal_runner, "_memory_recall", lambda query: "")


class _Sink:
    def __init__(self, path: Path) -> None:
        self.store = ArmTelegramStore(path)
        self.messages: list[str] = []

    def notify(self, task_id: str, kind: str, message: str) -> None:
        self.messages.append(message)


def test_restart_is_pending_and_abort_cancels(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 7, "restart the pipeline")
    caller = _Caller([])
    sink = _Sink(tmp_path / "telegram.sqlite3")
    result = poll_personal_tasks(tmp_path, sink, caller)
    assert result is not None and result.status == "pending"
    assert caller.bodies == [], "no model call before the operator confirms"
    task = PersonalStore(tmp_path).get(result.task_id)
    assert task is not None and task.status == "pending" and task.tool_log == "[]"
    pending = sink.store.pending_control_requests(result.task_id)
    assert [row.verb for row in pending] == ["personal"]
    assert apply_personal_decision(tmp_path, result.task_id, "abort") == "cancelled"
    assert PersonalStore(tmp_path).get(result.task_id).status == "cancelled"  # type: ignore[union-attr]


def test_the_confirm_prompt_names_the_request(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 7, "restart the pipeline")
    sink = _Sink(tmp_path / "telegram.sqlite3")
    result = poll_personal_tasks(tmp_path, sink, _Caller([]))
    assert result is not None
    assert any("restart the pipeline" in message for message in sink.messages)


def test_confirm_holds_without_a_tool_call(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 7, "restart the pipeline")
    caller = _Caller([])
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
    assert caller.bodies == []


def test_hidden_fleet_is_rejected_before_any_model_call(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 7, "check binresearch for the vm")
    caller = _Caller([])
    result = poll_personal_tasks(tmp_path, _Sink(tmp_path / "telegram.sqlite3"), caller)
    assert result is not None and result.status == "rejected"
    assert caller.bodies == []
    stored = PersonalStore(tmp_path).get(result.task_id)
    assert stored is not None and stored.tool_log == "[]"


def test_a_code_request_waits_for_confirm_then_runs_on_the_coding_seat(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 7, "run this python snippet over the task files")
    caller = _Caller([Completion("Found three files.", (), 1, ("execute_python",))])
    sink = _Sink(tmp_path / "telegram.sqlite3")
    pending = poll_personal_tasks(tmp_path, sink, caller)
    assert pending is not None and pending.status == "pending"
    assert caller.bodies == [], "the sandbox never runs before the confirm"
    assert apply_personal_decision(tmp_path, pending.task_id, "confirm") == "confirmed"

    result = poll_personal_tasks(tmp_path, sink, caller)

    assert result is not None and result.status == "done"
    assert caller.bodies[-1]["model"] == CODE_WORKSPACE
    assert "execute_python" in caller.bodies[-1]["portal_bite_tools"]  # type: ignore[operator]
    receipt = json.loads((tmp_path / pending.task_id / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["final_text"] == "Found three files."
    assert receipt["final_text"] != HELD_TEXT


def test_named_external_fleets_require_confirmation_instead_of_denial() -> None:
    assert text_gate("use unifi", frozenset()) == "confirm"
    assert text_gate("use browser", frozenset()) == "confirm"
    # 2026-11-20: a read-only proxmox question answers without a confirm prompt; a mutating
    # proxmox request still waits for one (see the tests below).
    assert text_gate("list the Proxmox VMs that are currently stopped", frozenset()) == "allow"
    assert text_gate("git_status the worktree", frozenset()) == "allow"


def test_read_only_proxmox_runs_without_confirm(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 7, "list the Proxmox VMs that are currently stopped")
    caller = _Caller([Completion("vm 100 is stopped.", (), 1, ("proxmox_list_vms",))])
    sink = _Sink(tmp_path / "telegram.sqlite3")

    result = poll_personal_tasks(tmp_path, sink, caller, recall=lambda query: "")

    assert result is not None and result.status == "done"
    assert "proxmox_list_vms" in caller.bodies[0]["portal_bite_tools"]  # type: ignore[operator]


def test_a_mutating_proxmox_request_waits_for_confirm(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 7, "snapshot the throwaway vm")
    caller = _Caller([])
    sink = _Sink(tmp_path / "telegram.sqlite3")

    result = poll_personal_tasks(tmp_path, sink, caller, recall=lambda query: "")

    assert result is not None and result.status == "pending"
    assert caller.bodies == [], "no tool ran before the confirm"


def test_read_only_git_runs_without_confirm(tmp_path: Path) -> None:
    """J-R2: git_status/git_log/git_diff are open; only mutations confirm."""
    telegram_do_reply(tmp_path, 7, "git status of the worktree in one paragraph")
    caller = _Caller(
        [Completion("The worktree is clean on the lane branch.", (), 1, ("git_status",))]
    )
    sink = _Sink(tmp_path / "telegram.sqlite3")
    result = poll_personal_tasks(tmp_path, sink, caller, recall=lambda query: "")
    assert result is not None and result.status == "done"
    task = PersonalStore(tmp_path).get(result.task_id)
    assert task is not None and task.status == "done"


def test_a_git_push_request_waits_for_confirm(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 7, "git commit and push the prepared change")
    caller = _Caller([])
    sink = _Sink(tmp_path / "telegram.sqlite3")
    result = poll_personal_tasks(tmp_path, sink, caller, recall=lambda query: "")
    assert result is not None and result.status == "pending"
    assert caller.bodies == []
    task = PersonalStore(tmp_path).get(result.task_id)
    assert task is not None and task.tool_log == "[]"
    stored = json.loads(task.plan_json or "{}")
    assert stored["needs_confirm"] is True
    assert "git_commit" not in stored["tools"], "a mutating tool is never offered"


def test_a_unifi_request_waits_for_confirm_before_any_tool_call(tmp_path: Path) -> None:
    """No bundle lists unifi tools yet; the request still cannot act unconfirmed."""
    telegram_do_reply(tmp_path, 7, "read the unifi device list")
    caller = _Caller([])
    sink = _Sink(tmp_path / "telegram.sqlite3")
    result = poll_personal_tasks(tmp_path, sink, caller, recall=lambda query: "")
    assert result is not None and result.status == "pending"
    assert caller.bodies == []


def test_memory_is_recalled_once_and_remember_runs_only_after_confirm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portal.modules.orchestration import personal_runner

    queries: list[str] = []

    def recall(query: str) -> str:
        queries.append(query)
        return "- Recalled no matching preference."

    monkeypatch.setattr(personal_runner, "_memory_recall", recall)
    telegram_do_reply(tmp_path, 7, "remember that I want Telegram replies under 400 characters")
    caller = _Caller([Completion("Saved the preference.", (), 1, ("remember",))])
    sink = _Sink(tmp_path / "telegram.sqlite3")

    pending = poll_personal_tasks(tmp_path, sink, caller)

    assert pending is not None and pending.status == "pending"
    assert len(queries) == 1
    assert "operator id 7" in queries[0]
    assert "Telegram replies under 400 characters" in queries[0]
    assert caller.bodies == [], "remember is not offered before the confirm"

    assert apply_personal_decision(tmp_path, pending.task_id, "confirm") == "confirmed"
    finished = poll_personal_tasks(tmp_path, sink, caller)

    assert finished is not None and finished.status == "done"
    assert (
        len(queries) == 1
    )  # the confirmed path reuses the stored memory, it does not recall again
    assert "Recalled no matching preference." in caller.bodies[-1]["messages"][-1]["content"]  # type: ignore[index]
    assert "remember" in caller.bodies[-1]["portal_bite_tools"]  # type: ignore[operator]


def test_personal_cloud_handoff_follows_two_local_failure_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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

    telegram_do_reply(tmp_path, 7, "help with an empty answer")
    caller = _Caller([Completion("", (), 0), Completion("", (), 0)])
    sink = _Sink(tmp_path / "telegram.sqlite3")
    dispatcher = Dispatcher()
    monkeypatch.setattr(personal_runner, "_personal_cloud_enabled", lambda: True, raising=False)

    first = poll_personal_tasks(tmp_path, sink, caller)
    second = poll_personal_tasks(tmp_path, sink, caller, dispatcher=dispatcher)

    assert first is not None and first.status == "retrying"
    assert second is not None and second.status == "done"
    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0]["tier"] == "auto"
    receipt = json.loads((tmp_path / second.task_id / "receipt.json").read_text(encoding="utf-8"))
    assert len(receipt["local_attempts"]) == 2
    brief = Path(str(dispatcher.calls[0]["brief"]))
    assert "empty final answer" in brief.read_text(encoding="utf-8")


def test_personal_cloud_retry_stops_if_flag_is_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from portal.modules.orchestration import personal_runner

    class Dispatcher:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, **kwargs: object) -> SimpleNamespace:
            self.calls += 1
            return SimpleNamespace(exit_code=1, status="failed", model="mock", result_text="failed")

    telegram_do_reply(tmp_path, 7, "help with an empty answer")
    caller = _Caller([Completion("", (), 0), Completion("", (), 0)])
    sink = _Sink(tmp_path / "telegram.sqlite3")
    dispatcher = Dispatcher()
    enabled = True
    monkeypatch.setattr(personal_runner, "_personal_cloud_enabled", lambda: enabled, raising=False)
    # Cap 2 keeps the retry path reachable; the shipped default cap is 1 (one cloud try).
    monkeypatch.setattr(personal_runner, "_personal_cloud_cap", lambda: 2, raising=False)

    assert poll_personal_tasks(tmp_path, sink, caller).status == "retrying"  # type: ignore[union-attr]
    assert (
        poll_personal_tasks(tmp_path, sink, caller, dispatcher=dispatcher).status == "cloud-retry"
    )  # type: ignore[union-attr]
    assert dispatcher.calls == 1

    enabled = False
    result = poll_personal_tasks(tmp_path, sink, caller, dispatcher=dispatcher)

    assert result is not None and result.status == "blocked"
    assert dispatcher.calls == 1
