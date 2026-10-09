"""review.runs -- durable, asynchronous review runs.

The compliance core's run lifecycle, for the reviewer: ``start`` returns a run id at once; a
worker thread does the work; ``status`` reads progress without re-running anything; ``result``
reads the persisted result; ``cancel`` takes effect at the next checkpoint. A restart marks
unfinished runs ``INTERRUPTED`` -- recovery is explicit and never masquerades as completion.

Why it exists: the hunt loop left 38 hunts stuck in ``running`` forever because nothing owned
their lifecycle. A review over a day of telemetry takes minutes to hours; a synchronous call is
not a product contract.

Stdlib only (sqlite3 + threading) so it is trivially testable.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


TERMINAL = frozenset(
    {RunStatus.COMPLETE, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.INTERRUPTED}
)


class RunCancelled(Exception):  # noqa: N818 -- control flow, not an error
    """Raised inside a runner at a checkpoint after cancellation was requested."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    request_json TEXT NOT NULL,
    result_json TEXT,
    error TEXT NOT NULL DEFAULT '',
    progress_json TEXT NOT NULL DEFAULT '{}',
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    heartbeat_at REAL NOT NULL
)
"""


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    status: RunStatus
    request: dict[str, Any]
    result: dict[str, Any] | None
    error: str
    progress: dict[str, Any]
    created_at: float
    updated_at: float
    heartbeat_at: float


class RunStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            if str(path) != ":memory:":
                self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute(_SCHEMA)
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _row(self, row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            run_id=row["run_id"],
            status=RunStatus(row["status"]),
            request=json.loads(row["request_json"]),
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            error=row["error"],
            progress=json.loads(row["progress_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            heartbeat_at=row["heartbeat_at"],
        )

    def create(self, request: Mapping[str, Any]) -> str:
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._lock:
            self._db.execute(
                "INSERT INTO review_runs (run_id, status, request_json, created_at, updated_at,"
                " heartbeat_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    RunStatus.QUEUED.value,
                    json.dumps(dict(request), default=str),
                    now,
                    now,
                    now,
                ),
            )
            self._db.commit()
        return run_id

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM review_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return self._row(row) if row else None

    def list(self, *, limit: int = 50, status: RunStatus | None = None) -> list[RunRecord]:
        query = "SELECT * FROM review_runs"
        args: tuple[Any, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            args = (status.value,)
        query += " ORDER BY created_at DESC LIMIT ?"
        with self._lock:
            rows = self._db.execute(query, (*args, limit)).fetchall()
        return [self._row(r) for r in rows]

    def _set(self, run_id: str, status: RunStatus, **cols: Any) -> None:
        now = time.time()
        sets = ["status = ?", "updated_at = ?", "heartbeat_at = ?"]
        vals: list[Any] = [status.value, now, now]
        for name, value in cols.items():
            sets.append(f"{name} = ?")
            vals.append(value)
        vals.append(run_id)
        with self._lock:
            self._db.execute(f"UPDATE review_runs SET {', '.join(sets)} WHERE run_id = ?", vals)
            self._db.commit()

    def mark_running(self, run_id: str) -> None:
        self._set(run_id, RunStatus.RUNNING)

    def progress(self, run_id: str, progress: Mapping[str, Any]) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE review_runs SET progress_json = ?, heartbeat_at = ? WHERE run_id = ?",
                (json.dumps(dict(progress), default=str), time.time(), run_id),
            )
            self._db.commit()

    def complete(self, run_id: str, result: Mapping[str, Any]) -> None:
        self._set(run_id, RunStatus.COMPLETE, result_json=json.dumps(dict(result), default=str))

    def fail(self, run_id: str, error: str) -> None:
        self._set(run_id, RunStatus.FAILED, error=error)

    def mark_cancelled(self, run_id: str) -> None:
        self._set(run_id, RunStatus.CANCELLED)

    def request_cancel(self, run_id: str) -> bool:
        """QUEUED runs cancel at once; RUNNING runs cancel at their next checkpoint."""
        record = self.get(run_id)
        if record is None or record.status in TERMINAL:
            return False
        if record.status == RunStatus.QUEUED:
            self.mark_cancelled(run_id)
            return True
        with self._lock:
            self._db.execute(
                "UPDATE review_runs SET cancel_requested = 1 WHERE run_id = ?", (run_id,)
            )
            self._db.commit()
        return True

    def cancel_requested(self, run_id: str) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT cancel_requested FROM review_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return bool(row and row["cancel_requested"])

    def mark_interrupted(self) -> int:
        """At process start: anything still QUEUED/RUNNING belonged to a dead process."""
        with self._lock:
            cur = self._db.execute(
                "UPDATE review_runs SET status = ?, error = ?, updated_at = ? WHERE status IN (?, ?)",
                (
                    RunStatus.INTERRUPTED.value,
                    "process restarted before the run finished",
                    time.time(),
                    RunStatus.QUEUED.value,
                    RunStatus.RUNNING.value,
                ),
            )
            self._db.commit()
            return cur.rowcount


@dataclass
class RunContext:
    run_id: str
    store: RunStore

    def check_cancel(self) -> None:
        if self.store.cancel_requested(self.run_id):
            raise RunCancelled(self.run_id)

    def report(self, stage: str, done: int, total: int) -> None:
        self.store.progress(self.run_id, {"stage": stage, "done": done, "total": total})


Runner = Callable[[Mapping[str, Any], RunContext], Mapping[str, Any]]


class RunWorker:
    """Runs ``runner(request, ctx)`` on a daemon thread per run and records the outcome."""

    def __init__(self, store: RunStore, runner: Runner) -> None:
        self.store = store
        self.runner = runner
        self._threads: dict[str, threading.Thread] = {}

    def start(self, request: Mapping[str, Any]) -> str:
        run_id = self.store.create(request)
        thread = threading.Thread(target=self._execute, args=(run_id,), daemon=True, name=run_id)
        self._threads[run_id] = thread
        thread.start()
        return run_id

    def join(self, run_id: str, timeout: float | None = None) -> None:
        thread = self._threads.get(run_id)
        if thread is not None:
            thread.join(timeout)

    def _execute(self, run_id: str) -> None:
        record = self.store.get(run_id)
        if record is None or record.status != RunStatus.QUEUED:
            return
        self.store.mark_running(run_id)
        ctx = RunContext(run_id, self.store)
        try:
            result = self.runner(record.request, ctx)
        except RunCancelled:
            self.store.mark_cancelled(run_id)
        except Exception as exc:  # noqa: BLE001 -- a failed run is recorded, never lost
            self.store.fail(run_id, f"{type(exc).__name__}: {exc}")
        else:
            if self.store.cancel_requested(run_id):
                self.store.mark_cancelled(run_id)
            else:
                self.store.complete(run_id, result)
