"""Shared SQLite outbox for orchestration notices and Telegram decisions."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import unicodedata
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

    def __init__(self, path: Path, approval_ttl_seconds: int | None = None) -> None:
        self.path = path
        self.approval_ttl_seconds = _approval_ttl_seconds(approval_ttl_seconds)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            self._create_schema(db)

    def request_approval(
        self,
        task_id: str,
        bite_id: str,
        bite_definition: dict[str, Any],
        reason: str,
        run_id: str,
    ) -> bool | None:
        canonical = json.dumps(
            {"bite": bite_definition, "reason": reason}, sort_keys=True, separators=(",", ":")
        )
        content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        message = (
            f"Approve orchestration bite?\nTask: {_safe_notice_text(task_id)}\n"
            f"Bite: {_safe_notice_text(bite_id)}\nContent: {content_hash[:12]}\n"
            f"Reason: {_safe_notice_text(reason)}"
        )
        while True:
            request_id = self._enqueue(task_id, bite_id, "approval", message, content_hash, run_id)
            with self._db() as db:
                row = db.execute(
                    "SELECT status, decision, created_at FROM arm_notice WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
            if row is None:
                return False
            if row[0] == "expired":
                continue
            if row[0] not in {"queued", "pending", "approved"} or not self._expired(str(row[2])):
                break
        if row[0] in {"queued", "pending"} and row[1] is None:
            return None
        return row[0] == "approved" and row[1] == "approve"

    def blocked(self, task_id: str, bite_id: str, failure: dict[str, Any]) -> None:
        text = (
            f"Orchestration bite blocked.\nTask: {_safe_notice_text(task_id)}\n"
            f"Bite: {_safe_notice_text(bite_id)}\nFailure: {_safe_notice_text(failure)}"
        )
        self._enqueue(task_id, bite_id, "blocked", text, "", "")

    def outbox(self) -> list[ArmNotice]:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT request_id, created_at FROM arm_notice WHERE kind = 'approval' "
                "AND status = 'queued'"
            ).fetchall()
            for request_id, created_at in rows:
                if self._expired(str(created_at)):
                    db.execute(
                        "UPDATE arm_notice SET status = 'expired' WHERE request_id = ?",
                        (request_id,),
                    )
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
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT created_at FROM arm_notice WHERE request_id = ? "
                "AND kind = 'approval' AND status = 'pending'",
                (request_id,),
            ).fetchone()
            if row is None:
                return False
            if self._expired(str(row[0])):
                db.execute(
                    "UPDATE arm_notice SET status = 'expired' WHERE request_id = ?",
                    (request_id,),
                )
                return False
            cursor = db.execute(
                "UPDATE arm_notice SET status = ?, decision = ? WHERE request_id = ? "
                "AND kind = 'approval' AND status = 'pending'",
                ("approved" if decision == "approve" else "denied", decision, request_id),
            )
            return cursor.rowcount == 1

    def _enqueue(
        self,
        task_id: str,
        bite_id: str,
        kind: str,
        message: str,
        content_hash: str,
        run_id: str,
    ) -> str:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT request_id, status, created_at FROM arm_notice WHERE task_id = ? "
                "AND bite_id = ? AND kind = ? AND content_hash = ? AND run_id = ? "
                "ORDER BY rowid DESC LIMIT 1",
                (task_id, bite_id, kind, content_hash, run_id),
            ).fetchone()
            if row is not None:
                request_id, status, created_at = row
                if kind == "approval":
                    if status == "expired":
                        pass
                    elif status in {"queued", "pending", "approved"} and self._expired(
                        str(created_at)
                    ):
                        db.execute(
                            "UPDATE arm_notice SET status = 'expired' WHERE request_id = ?",
                            (request_id,),
                        )
                    else:
                        return str(request_id)
                else:
                    return str(request_id)
            request_id = uuid.uuid4().hex
            db.execute(
                "INSERT INTO arm_notice (request_id, task_id, bite_id, kind, message, status, "
                "decision, created_at, content_hash, run_id) "
                "VALUES (?, ?, ?, ?, ?, 'queued', NULL, ?, ?, ?)",
                (request_id, task_id, bite_id, kind, message, _now(), content_hash, run_id),
            )
        return request_id

    def _create_schema(self, db: sqlite3.Connection) -> None:
        columns = {str(row[1]) for row in db.execute("PRAGMA table_info(arm_notice)")}
        has_identity = {"content_hash", "run_id"}.issubset(columns)
        has_old_unique_key = False
        for index in db.execute("PRAGMA index_list(arm_notice)"):
            if not index[2]:
                continue
            name = str(index[1]).replace('"', '""')
            fields = tuple(str(info[2]) for info in db.execute(f'PRAGMA index_info("{name}")'))
            if fields == ("task_id", "bite_id", "kind"):
                has_old_unique_key = True
                break
        if columns and (not has_identity or has_old_unique_key):
            db.execute("ALTER TABLE arm_notice RENAME TO arm_notice_legacy")
            self._create_notice_table(db)
            identity_fields = (
                "content_hash, run_id"
                if has_identity
                else "CASE WHEN kind = 'approval' THEN 'legacy' ELSE '' END, "
                "CASE WHEN kind = 'approval' THEN 'legacy' ELSE '' END"
            )
            if has_identity:
                status_field = "status"
            else:
                status_field = (
                    "CASE WHEN kind = 'approval' AND status IN "
                    "('queued', 'pending', 'approved') THEN 'expired' ELSE status END"
                )
            db.execute(
                "INSERT INTO arm_notice (request_id, task_id, bite_id, kind, message, status, "
                "decision, created_at, content_hash, run_id) "
                f"SELECT request_id, task_id, bite_id, kind, message, {status_field}, "
                f"decision, created_at, {identity_fields} "
                "FROM arm_notice_legacy"
            )
            db.execute("DROP TABLE arm_notice_legacy")
        elif not columns:
            self._create_notice_table(db)
        db.execute(
            "CREATE INDEX IF NOT EXISTS arm_notice_identity "
            "ON arm_notice(task_id, bite_id, kind, content_hash, run_id)"
        )

    def _create_notice_table(self, db: sqlite3.Connection) -> None:
        db.execute(
            """CREATE TABLE arm_notice (
                request_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                bite_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL,
                decision TEXT,
                created_at TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                run_id TEXT NOT NULL
            )"""
        )

    def _expired(self, created_at: str) -> bool:
        try:
            created = datetime.fromisoformat(created_at)
        except ValueError:
            return True
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return (datetime.now(UTC) - created).total_seconds() >= self.approval_ttl_seconds

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
    configured = os.environ.get("PORTAL_ARM_TELEGRAM_DB")
    if configured:
        return Path(configured).expanduser()
    output_root = Path(os.environ.get("AI_OUTPUT_DIR", "~/AI_Output")).expanduser()
    return output_root / ".portal_arm" / "telegram.sqlite3"


def _approval_ttl_seconds(configured: int | None) -> int:
    raw = (
        configured
        if configured is not None
        else os.environ.get("PORTAL_ARM_APPROVAL_TTL_SECONDS", "1800")
    )
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("approval TTL must be a positive integer number of seconds") from exc
    if value <= 0:
        raise ValueError("approval TTL must be a positive integer number of seconds")
    return value


def _safe_notice_text(value: object) -> str:
    escapes = {"\n": r"\n", "\r": r"\r", "\t": r"\t"}
    return "".join(
        escapes.get(char, f"\\x{ord(char):02x}") if unicodedata.category(char) == "Cc" else char
        for char in str(value)
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
