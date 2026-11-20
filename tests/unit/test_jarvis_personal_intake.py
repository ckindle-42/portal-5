"""J2: a personal task row, separate from the arm queue ledger."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from portal.modules.orchestration.personal_intake import enqueue_personal, telegram_do_reply
from portal.modules.orchestration.personal_store import PersonalStore
from portal.modules.orchestration.queue import QueueLedger


def test_do_is_not_an_arm_control_verb() -> None:
    pytest.importorskip("telegram")
    from portal.modules.orchestration.control import VERB_NAMES
    from portal_channels.telegram.jarvis_control import parse

    assert parse("/jarvis do what is the queue status") == ("do", "what is the queue status")
    assert parse("/jarvis do") == ("do", "")
    assert "do" not in VERB_NAMES
    assert parse("/jarvis bogus") == ("bogus", "")


def test_empty_do_writes_no_row(tmp_path: Path) -> None:
    assert telegram_do_reply(tmp_path, 7, "  ") == "Usage: /jarvis do <text>"
    assert not (tmp_path / "personal_tasks.sqlite3").exists()


def test_telegram_do_queues_one_row_and_leaves_the_arm_ledger_empty(tmp_path: Path) -> None:
    root = tmp_path
    reply = telegram_do_reply(root, 42, "what is the queue status in one paragraph")
    task_id = reply.removeprefix("queued ")
    assert reply == f"queued {task_id}"
    task = PersonalStore(root).get(task_id)
    assert task is not None
    assert task.source == "telegram"
    assert task.user_id == "42"
    assert task.text == "what is the queue status in one paragraph"
    assert task.status == "queued"
    assert task.plan_json is None
    with QueueLedger(root) as ledger:
        assert ledger.items() == []
    assert not _table_exists(root / "queue.sqlite3", "personal_tasks")


def test_owui_submit_requires_the_allowlisted_telegram_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portal.modules.orchestration import owui_entry

    root = tmp_path
    monkeypatch.setenv("TELEGRAM_USER_IDS", "42")
    monkeypatch.setattr(owui_entry, "tasks_root", lambda: root)
    refused = owui_entry.jarvis_submit("hello", "99")
    assert refused == {"error": "unauthorized"}
    assert PersonalStore(root).oldest_runnable() is None
    accepted = owui_entry.jarvis_submit("hello from owui", "42")
    assert str(accepted["reply"]).startswith("queued ")
    task = PersonalStore(root).get(str(accepted["id"]))
    assert task is not None
    assert task.source == "owui"
    assert task.user_id == "42"
    empty = owui_entry.jarvis_submit("  ", "42")
    assert "error" in empty
    assert enqueue_personal(root, "owui", "42", "second").startswith("pt-")


def test_unknown_source_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source"):
        enqueue_personal(tmp_path, "email", "1", "hello")


@pytest.mark.parametrize(
    "text",
    [
        "run docker compose down -v",
        "docker system prune -af",
        "rm -rf ~/projects/portal-5",
        "launch.sh down",
        "git push --force origin main",
    ],
)
def test_a_destructive_request_is_refused_and_the_operator_is_told(
    tmp_path: Path, text: str
) -> None:
    """2026-11-20: `docker compose down -v` vanished without a word; now it is answered."""
    from portal.modules.orchestration.personal_intake import telegram_do

    reply, task_id = telegram_do(tmp_path, 7, text)

    assert reply.startswith("refused: ")
    assert "Nothing was queued" in reply
    assert task_id is None
    assert PersonalStore(tmp_path).oldest_runnable() is None


def test_the_owui_submit_reports_a_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from portal.modules.orchestration import owui_entry

    monkeypatch.setenv("TELEGRAM_USER_IDS", "42")
    monkeypatch.setattr(owui_entry, "tasks_root", lambda: tmp_path)

    answer = owui_entry.jarvis_submit("docker compose down -v", "42")

    assert "refused:" in str(answer["error"])
    assert PersonalStore(tmp_path).oldest_runnable() is None


def test_a_question_about_a_destructive_command_is_not_refused(tmp_path: Path) -> None:
    """A read-only question that names a dangerous command is still a question."""
    from portal.modules.orchestration.personal_intake import telegram_do

    reply, task_id = telegram_do(tmp_path, 7, "explain what docker compose down -v does")

    assert task_id is not None and reply == f"queued {task_id}"


def test_a_queued_task_reports_its_queue_position(tmp_path: Path) -> None:
    from portal.modules.orchestration.personal_intake import (
        personal_queue_note,
        telegram_do,
    )

    _first, first_id = telegram_do(tmp_path, 7, "what is the queue status")
    third = telegram_do(tmp_path, 7, "list the newest receipts")[1]
    assert third is not None

    reply, second_id = telegram_do(tmp_path, 7, "what is the queue status in one paragraph")

    assert second_id is not None and reply == f"queued {second_id}"
    assert personal_queue_note(tmp_path, second_id) == "Queue position: 3"
    assert PersonalStore(tmp_path).live_position(first_id or "") == 1


def test_intake_reports_a_queued_task_id_for_the_bot_to_annotate(tmp_path: Path) -> None:
    from portal.modules.orchestration.personal_intake import telegram_do

    reply, task_id = telegram_do(tmp_path, 7, "what is the queue status")

    assert task_id is not None and reply == f"queued {task_id}"
    assert telegram_do(tmp_path, 7, "  ") == ("Usage: /jarvis do <text>", None)


def test_telegram_do_stores_utc_not_before_and_skips_until_due(tmp_path: Path) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    due = now + timedelta(minutes=2)
    reply = telegram_do_reply(tmp_path, 7, f"at {due.isoformat()} send me queue status")
    task = PersonalStore(tmp_path).get(reply.removeprefix("queued "))

    assert task is not None
    assert task.text == "send me queue status"
    assert task.not_before == due.isoformat()
    assert PersonalStore(tmp_path).oldest_runnable(now=now) is None
    assert PersonalStore(tmp_path).oldest_runnable(now=due + timedelta(seconds=1)).id == task.id


def test_runner_leaves_reminder_queued_until_the_due_poll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from portal.modules.orchestration import personal_runner
    from portal.modules.orchestration.personal_runner import Completion, poll_personal_tasks

    monkeypatch.setattr(personal_runner, "_memory_recall", lambda query: "")

    class Caller:
        def __init__(self) -> None:
            self.replies = [
                Completion(json.dumps({"steps": [{"tools": ["queue_status"]}]}), (), 0),
                Completion(
                    "",
                    ({"id": "c1", "function": {"name": "queue_status", "arguments": "{}"}},),
                    0,
                ),
                Completion("Queue is empty.", (), 0),
            ]

        def complete(self, body: dict[str, object]) -> Completion:
            return self.replies.pop(0)

    class Notices:
        def notify(self, task_id: str, kind: str, message: str) -> None:
            return None

    now = datetime.now(UTC).replace(microsecond=0)
    due = now + timedelta(minutes=2)
    reply = telegram_do_reply(tmp_path, 7, f"at {due.isoformat()} send me queue status")
    task_id = reply.removeprefix("queued ")
    caller = Caller()

    assert poll_personal_tasks(tmp_path, Notices(), caller, now=now) is None
    task = PersonalStore(tmp_path).get(task_id)
    assert task is not None and task.status == "queued" and task.receipt_path is None

    result = poll_personal_tasks(tmp_path, Notices(), caller, now=due + timedelta(seconds=1))

    assert result is not None and result.status == "done"
    assert PersonalStore(tmp_path).get(task_id).status == "done"  # type: ignore[union-attr]


def _table_exists(path: Path, name: str) -> bool:
    file = path
    if not file.is_file():
        return False
    with sqlite3.connect(file) as db:
        row = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
    return row is not None
