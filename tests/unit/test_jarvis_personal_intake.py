"""J2: a personal task row, separate from the arm queue ledger."""

from __future__ import annotations

import sqlite3
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


def _table_exists(path: Path, name: str) -> bool:
    file = path
    if not file.is_file():
        return False
    with sqlite3.connect(file) as db:
        row = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
    return row is not None
