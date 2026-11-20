"""Personal task rows beside the arm queue.

The arm ledger stays ``queue.sqlite3``. These rows live in ``personal_tasks.sqlite3``
in the same tasks directory.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_SOURCES = frozenset({"telegram", "owui"})
_RUNNABLE = frozenset({"queued", "confirmed", "cloud_retry"})
# A cloud lane that has not reported yet. ``handed-to-cloud`` is the same state as
# written by the blocking dispatcher before the poll-based handoff existed.
_IN_FLIGHT_CLOUD = ("cloud-running", "handed-to-cloud")
# Every status the runner will still act on, for the queue position an operator sees.
_LIVE = ("queued", "confirmed", "pending", "running", "cloud_retry") + _IN_FLIGHT_CLOUD
_COLUMNS = (
    "id, source, user_id, text, status, plan_json, receipt_path, created, tool_log, not_before"
)


@dataclass(frozen=True)
class PersonalTask:
    id: str
    source: str
    user_id: str
    text: str
    status: str
    plan_json: str | None
    receipt_path: str | None
    created: str
    tool_log: str
    not_before: str | None = None


class PersonalStore:
    """One sqlite file of personal tasks. Does not open the arm queue ledger."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "personal_tasks.sqlite3"

    def add(
        self, source: str, user_id: str, text: str, not_before: datetime | str | None = None
    ) -> PersonalTask:
        if source not in _SOURCES:
            raise ValueError(f"source must be telegram or owui, got {source}")
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("text must be non-empty")
        task_id = "pt-" + uuid.uuid4().hex[:12]
        created = _now()
        due = _utc_stamp(not_before) if not_before is not None else None
        with self._db() as db:
            db.execute(
                "INSERT INTO personal_tasks (id, source, user_id, text, status, plan_json, "
                "receipt_path, created, tool_log, not_before) "
                "VALUES (?, ?, ?, ?, 'queued', NULL, NULL, ?, '[]', ?)",
                (task_id, source, user_id, cleaned, created, due),
            )
        task = self.get(task_id)
        if task is None:
            raise RuntimeError(f"personal task {task_id} was not stored")
        return task

    def get(self, task_id: str) -> PersonalTask | None:
        with self._db() as db:
            row = db.execute(
                f"SELECT {_COLUMNS} FROM personal_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return _task(row) if row is not None else None

    def in_flight_cloud(self) -> list[PersonalTask]:
        """Rows whose cloud lane has not reported a result yet, oldest first."""
        query = (
            f"SELECT {_COLUMNS} FROM personal_tasks "
            f"WHERE status IN ({', '.join('?' for _ in _IN_FLIGHT_CLOUD)}) "
            "ORDER BY created, rowid"
        )
        with self._db() as db:
            rows = db.execute(query, _IN_FLIGHT_CLOUD).fetchall()
        return [_task(row) for row in rows]

    def live_position(self, task_id: str) -> int:
        """1-based place of one row among the unfinished rows, or 0 when it is not live."""
        query = (
            "SELECT COUNT(*) FROM personal_tasks WHERE "
            f"status IN ({', '.join('?' for _ in _LIVE)}) AND "
            "(created < ? OR (created = ? AND rowid <= ?))"
        )
        with self._db() as db:
            row = db.execute(
                "SELECT created, rowid, status FROM personal_tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None or str(row[2]) not in _LIVE:
                return 0
            found = db.execute(query, (*_LIVE, str(row[0]), str(row[0]), int(row[1]))).fetchone()
        return int(found[0]) if found is not None else 0

    def oldest_runnable(self, now: datetime | None = None) -> PersonalTask | None:
        """Oldest due queued or operator-confirmed row. Pending rows stay put."""
        stamp = _utc_stamp(now or datetime.now(UTC))
        with self._db() as db:
            row = db.execute(
                f"SELECT {_COLUMNS} FROM personal_tasks "
                "WHERE status IN ('queued', 'confirmed', 'cloud_retry') "
                "AND (not_before IS NULL OR not_before <= ?) "
                "ORDER BY CASE status WHEN 'confirmed' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END, "
                "created, rowid LIMIT 1",
                (stamp,),
            ).fetchone()
        return _task(row) if row is not None else None

    def update(
        self,
        task_id: str,
        *,
        status: str,
        plan_json: str | None = None,
        receipt_path: str | None = None,
        tool_log: str | None = None,
        expect: frozenset[str] | None = None,
    ) -> PersonalTask | None:
        """Update one row. Returns None when ``expect`` does not match the current status."""
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT status FROM personal_tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if current is None:
                return None
            if expect is not None and str(current[0]) not in expect:
                return None
            sets = ["status = ?"]
            values: list[str | None] = [status]
            if plan_json is not None:
                sets.append("plan_json = ?")
                values.append(plan_json)
            if receipt_path is not None:
                sets.append("receipt_path = ?")
                values.append(receipt_path)
            if tool_log is not None:
                sets.append("tool_log = ?")
                values.append(tool_log)
            values.append(task_id)
            db.execute(
                f"UPDATE personal_tasks SET {', '.join(sets)} WHERE id = ?",
                values,
            )
        return self.get(task_id)

    def _db(self) -> _Conn:
        self.root.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA busy_timeout = 5000")
        db.execute(
            """CREATE TABLE IF NOT EXISTS personal_tasks (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                user_id TEXT NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL,
                plan_json TEXT,
                receipt_path TEXT,
                created TEXT NOT NULL,
                tool_log TEXT NOT NULL DEFAULT '[]',
                not_before TEXT
            )"""
        )
        columns = {str(row[1]) for row in db.execute("PRAGMA table_info(personal_tasks)")}
        if "not_before" not in columns:
            db.execute("ALTER TABLE personal_tasks ADD COLUMN not_before TEXT")
        return _Conn(db)


class _Conn:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def __enter__(self) -> sqlite3.Connection:
        return self.db

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        try:
            if exc_type is None:
                self.db.commit()
            else:
                self.db.rollback()
        finally:
            self.db.close()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _utc_stamp(value: datetime | str) -> str:
    stamp = (
        datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    )
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("not_before must include a UTC offset")
    return stamp.astimezone(UTC).isoformat()


def _task(row: sqlite3.Row | tuple[object, ...]) -> PersonalTask:
    return PersonalTask(
        id=str(row[0]),
        source=str(row[1]),
        user_id=str(row[2]),
        text=str(row[3]),
        status=str(row[4]),
        plan_json=None if row[5] is None else str(row[5]),
        receipt_path=None if row[6] is None else str(row[6]),
        created=str(row[7]),
        tool_log=str(row[8]),
        not_before=None if row[9] is None else str(row[9]),
    )


def runnable_statuses() -> frozenset[str]:
    return _RUNNABLE
