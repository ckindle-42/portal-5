"""Shared SQLite outbox for orchestration notices and Telegram decisions."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ArmNotice:
    request_id: str
    kind: str
    task_id: str
    bite_id: str
    message: str


class TelegramSender(Protocol):
    async def send_message(self, **kwargs: Any) -> Any: ...


class ArmTelegramStore:
    """Persist messages and gate decisions shared by the host and bot container."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS arm_notice (
                    request_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    bite_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL,
                    decision TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(task_id, bite_id, kind)
                )"""
            )

    def request_approval(self, task_id: str, bite_id: str, reason: str) -> bool | None:
        message = f"Approve orchestration bite?\nTask: {task_id}\nBite: {bite_id}\nReason: {reason}"
        request_id = self._enqueue(task_id, bite_id, "approval", message)
        with self._db() as db:
            row = db.execute(
                "SELECT decision FROM arm_notice WHERE request_id = ?", (request_id,)
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return row[0] == "approve"

    def blocked(self, task_id: str, bite_id: str, failure: dict[str, Any]) -> None:
        text = f"Orchestration bite blocked.\nTask: {task_id}\nBite: {bite_id}\nFailure: {failure}"
        self._enqueue(task_id, bite_id, "blocked", text)

    def outbox(self) -> list[ArmNotice]:
        with self._db() as db:
            rows = db.execute(
                "SELECT request_id, kind, task_id, bite_id, message FROM arm_notice "
                "WHERE status = 'queued' ORDER BY created_at"
            ).fetchall()
        return [ArmNotice(*row) for row in rows]

    def mark_sent(self, request_id: str) -> None:
        with self._db() as db:
            db.execute(
                "UPDATE arm_notice SET status = CASE WHEN kind = 'approval' "
                "THEN 'pending' ELSE 'sent' END WHERE request_id = ? AND status = 'queued'",
                (request_id,),
            )

    def decide(self, request_id: str, decision: str, user_id: int, allowed_users: set[int]) -> bool:
        if decision not in {"approve", "deny"} or user_id not in allowed_users:
            return False
        with self._db() as db:
            cursor = db.execute(
                "UPDATE arm_notice SET status = ?, decision = ? WHERE request_id = ? "
                "AND kind = 'approval' AND status = 'pending'",
                ("approved" if decision == "approve" else "denied", decision, request_id),
            )
            return cursor.rowcount == 1

    def _enqueue(self, task_id: str, bite_id: str, kind: str, message: str) -> str:
        with self._db() as db:
            row = db.execute(
                "SELECT request_id FROM arm_notice WHERE task_id = ? AND bite_id = ? AND kind = ?",
                (task_id, bite_id, kind),
            ).fetchone()
            if row is not None:
                return str(row[0])
            request_id = uuid.uuid4().hex
            db.execute(
                "INSERT INTO arm_notice VALUES (?, ?, ?, ?, ?, 'queued', NULL, ?)",
                (request_id, task_id, bite_id, kind, message, _now()),
            )
        return request_id

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA busy_timeout = 5000")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


async def send_outbox_once(
    store: ArmTelegramStore,
    bot: TelegramSender,
    recipients: set[int],
    keyboard_factory: Any,
) -> int:
    """Send queued messages through the existing Telegram application's bot."""
    if not recipients:
        return 0
    count = 0
    for notice in store.outbox():
        markup = keyboard_factory(notice.request_id) if notice.kind == "approval" else None
        for user_id in sorted(recipients):
            await bot.send_message(chat_id=user_id, text=notice.message, reply_markup=markup)
        store.mark_sent(notice.request_id)
        count += 1
    return count


def default_arm_telegram_path() -> Path:
    """Return the AI_Output path mounted by the Telegram service at /workspace."""
    import os

    configured = os.environ.get("PORTAL_ARM_TELEGRAM_DB")
    if configured:
        return Path(configured).expanduser()
    output_root = Path(os.environ.get("AI_OUTPUT_DIR", "~/AI_Output")).expanduser()
    return output_root / ".portal_arm" / "telegram.sqlite3"


def _now() -> str:
    return datetime.now(UTC).isoformat()
