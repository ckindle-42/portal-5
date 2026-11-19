"""J5: risky personal steps wait for confirm and do not call tools. No network."""

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
        self.recall_bodies: list[dict[str, object]] = []
        self.recall_reply = Completion("No matching operator memory.", (), 1, ("recall",))

    def complete(self, body: dict[str, object]) -> Completion:
        saved = json.loads(json.dumps(body))
        if body.get("portal_bite_tools") == ["recall"]:
            self.recall_bodies.append(saved)
            return self.recall_reply
        self.bodies.append(saved)
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
    telegram_do_reply(tmp_path, 7, "check binresearch for the vm")
    caller = _Caller([])
    result = poll_personal_tasks(tmp_path, _Sink(tmp_path / "telegram.sqlite3"), caller)
    assert result is not None and result.status == "rejected"
    assert caller.bodies == []
    stored = PersonalStore(tmp_path).get(result.task_id)
    assert stored is not None and stored.tool_log == "[]"


def test_confirmed_validated_execute_bash_plan_runs(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 7, "list the three largest files in the task directory")
    caller = _Caller(
        [
            Completion(_plan("execute_bash"), (), 0),
            Completion("Found three files.", (), 1, ("execute_bash",)),
        ]
    )
    sink = _Sink(tmp_path / "telegram.sqlite3")
    pending = poll_personal_tasks(tmp_path, sink, caller)
    assert pending is not None and pending.status == "pending"
    assert apply_personal_decision(tmp_path, pending.task_id, "confirm") == "confirmed"

    result = poll_personal_tasks(tmp_path, sink, caller)

    assert result is not None and result.status == "done"
    assert len(caller.bodies) == 2
    assert caller.bodies[1]["model"] == CODE_WORKSPACE
    assert caller.bodies[1]["portal_bite_tools"] == ["execute_bash"]
    receipt = json.loads((tmp_path / pending.task_id / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["final_text"] == "Found three files."
    assert receipt["final_text"] != HELD_TEXT


def test_named_external_fleets_require_confirmation_instead_of_denial() -> None:
    for name in ("proxmox", "unifi", "browser", "git"):
        assert text_gate(f"use {name}", frozenset()) == "confirm"


def test_read_only_git_plan_runs_without_confirm(tmp_path: Path) -> None:
    """J-R2: git_status/git_log/git_diff are open; only mutations confirm."""
    telegram_do_reply(tmp_path, 7, "summarize the worktree state in one paragraph")
    caller = _Caller(
        [
            Completion(_plan("git_status"), (), 0),
            Completion("The worktree is clean on the lane branch.", (), 1, ("git_status",)),
        ]
    )
    sink = _Sink(tmp_path / "telegram.sqlite3")
    result = poll_personal_tasks(tmp_path, sink, caller)
    assert result is not None and result.status == "done"
    assert len(caller.bodies) == 2
    task = PersonalStore(tmp_path).get(result.task_id)
    assert task is not None and task.status == "done"


def test_git_commit_and_push_plans_wait_for_confirm(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 7, "land the prepared change in the other repo")
    two = json.dumps(
        {
            "steps": [
                {
                    "id": "step",
                    "tools": ["git_commit", "git_push"],
                    "paths": [],
                    "budget": {"context_tokens": 512},
                }
            ]
        }
    )
    caller = _Caller([Completion(two, (), 0)])
    sink = _Sink(tmp_path / "telegram.sqlite3")
    result = poll_personal_tasks(tmp_path, sink, caller)
    assert result is not None and result.status == "pending"
    task = PersonalStore(tmp_path).get(result.task_id)
    assert task is not None and task.tool_log == "[]"
    planned = set(json.loads(task.plan_json or "{}")["steps"][0]["tools"])
    assert planned == {"git_commit", "git_push"}


def test_unifi_plan_waits_for_confirm_then_runs_the_read(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 7, "read the unifi device list")
    caller = _Caller(
        [
            Completion(_plan("unifi_list_devices"), (), 0),
            Completion("Six devices online.", (), 1, ("unifi_list_devices",)),
        ]
    )
    sink = _Sink(tmp_path / "telegram.sqlite3")
    pending = poll_personal_tasks(tmp_path, sink, caller)
    assert pending is not None and pending.status == "pending"
    assert apply_personal_decision(tmp_path, pending.task_id, "confirm") == "confirmed"
    result = poll_personal_tasks(tmp_path, sink, caller)
    assert result is not None and result.status == "done"
    receipt = json.loads((tmp_path / pending.task_id / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["tool_calls"] == ["unifi_list_devices"]


def test_memory_is_recalled_once_and_remember_runs_only_after_confirm(tmp_path: Path) -> None:
    telegram_do_reply(tmp_path, 7, "remember that I want Telegram replies under 400 characters")
    caller = _Caller(
        [
            Completion(_plan("remember"), (), 0),
            Completion("Saved the preference.", (), 1, ("remember",)),
        ]
    )
    caller.recall_reply = Completion("Recalled no matching preference.", (), 1, ("recall",))
    sink = _Sink(tmp_path / "telegram.sqlite3")

    pending = poll_personal_tasks(tmp_path, sink, caller)

    assert pending is not None and pending.status == "pending"
    assert len(caller.recall_bodies) == 1
    assert caller.recall_bodies[0]["portal_bite_tools"] == ["recall"]
    assert caller.recall_bodies[0]["tool_choice"] == "required"
    assert "operator id 7" in caller.recall_bodies[0]["messages"][-1]["content"]
    assert "Recalled no matching preference." in caller.bodies[0]["messages"][-1]["content"]
    assert all("remember" not in body.get("portal_bite_tools", []) for body in caller.bodies)

    assert apply_personal_decision(tmp_path, pending.task_id, "confirm") == "confirmed"
    finished = poll_personal_tasks(tmp_path, sink, caller)

    assert finished is not None and finished.status == "done"
    assert caller.bodies[-1]["portal_bite_tools"] == ["remember"]


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
                exit_code=0, status="complete", model="mock", result_text="Cloud lane ran."
            )

    telegram_do_reply(tmp_path, 7, "help with an invalid local plan")
    caller = _Caller([Completion("not JSON", (), 0), Completion("still not JSON", (), 0)])
    sink = _Sink(tmp_path / "telegram.sqlite3")
    dispatcher = Dispatcher()
    monkeypatch.setattr(personal_runner, "_personal_cloud_enabled", lambda: True, raising=False)

    first = poll_personal_tasks(tmp_path, sink, caller)
    second = poll_personal_tasks(tmp_path, sink, caller, dispatcher=dispatcher)

    assert first is not None and first.status == "retrying"
    assert second is not None and second.status == "handed-to-cloud"
    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0]["tier"] == "auto"
    receipt = json.loads((tmp_path / second.task_id / "receipt.json").read_text(encoding="utf-8"))
    assert len(receipt["local_attempts"]) == 2
    brief = Path(str(dispatcher.calls[0]["brief"]))
    assert "not JSON" in brief.read_text(encoding="utf-8")
    assert "still not JSON" in brief.read_text(encoding="utf-8")


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

    telegram_do_reply(tmp_path, 7, "help with an invalid local plan")
    caller = _Caller([Completion("not JSON", (), 0), Completion("still not JSON", (), 0)])
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
