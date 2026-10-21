"""Persistent single-worker queue for unattended orchestration tasks."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import Bite, TaskPlan, parse_plan, plan_json
from .service import ArmService
from .worker import Engine, PipelineError

DEFAULT_PID_FILE = Path("/tmp/portal5-memory-safety-test-pids")
DEFAULT_LOCK_DIR = "~/.portal5/locks/"


@dataclass(frozen=True)
class QueueRun:
    status: str
    task_id: str | None = None
    receipt_path: Path | None = None
    reason: str | None = None


class QueueGate:
    """Yield queued bites to active bench runs, operator locks, or Pipeline load."""

    def __init__(
        self,
        engines: dict[str, Engine],
        policy: dict[str, Any],
        *,
        pid_file: Path = DEFAULT_PID_FILE,
    ) -> None:
        lock_dir = policy.get("yield_lock_dir", DEFAULT_LOCK_DIR)
        if not isinstance(lock_dir, str) or not lock_dir.strip():
            raise ValueError("queue.yield_lock_dir must be a non-empty path")
        self.engines = engines
        self.pid_file = pid_file
        self.lock_dir = Path(lock_dir).expanduser()
        self.last_reason: str | None = None

    def allows(self, bite: Bite) -> bool:
        self.last_reason = self._external_lock_reason()
        if self.last_reason:
            return False
        try:
            plan = self.engines[bite.model].load_plan(10)
        except PipelineError as exc:
            self.last_reason = f"Pipeline load-plan did not admit the bite: {exc}"
            return False
        if not isinstance(plan.get("busy"), bool):
            self.last_reason = "Pipeline load-plan did not report active traffic"
            return False
        if plan["busy"]:
            self.last_reason = "Pipeline reports interactive or queued inference traffic"
            return False
        if plan.get("fits") is not True:
            self.last_reason = "Pipeline load-plan reports no fit or unknown capacity"
            return False
        return True

    def _external_lock_reason(self) -> str | None:
        pids, error = _live_pids(self.pid_file)
        if error:
            return error
        if pids:
            return f"memory-safety run is active (pid {pids[0]})"
        try:
            locks = sorted(path for path in self.lock_dir.iterdir() if path.is_file())
        except FileNotFoundError:
            return None
        except OSError as exc:
            return f"cannot inspect queue yield-lock directory: {exc}"
        for lock in locks:
            pids, error = _live_pids(lock)
            if error:
                return error
            if pids:
                return f"yield lock {lock.name} is active (pid {pids[0]})"
        return None


class QueueLedger:
    """Store queued plans and queue state transitions in SQLite."""

    def __init__(self, task_root: Path) -> None:
        task_root.mkdir(parents=True, exist_ok=True)
        self.task_root = task_root
        self.db = sqlite3.connect(task_root / "queue.sqlite3", timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS queue_task (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL UNIQUE,
                plan_json TEXT NOT NULL,
                source_dir TEXT NOT NULL,
                state TEXT NOT NULL,
                runner_pid INTEGER,
                receipt_status TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS queue_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                state TEXT NOT NULL,
                detail_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self.db.commit()

    def __enter__(self) -> QueueLedger:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.db.close()

    def enqueue(self, plan: TaskPlan | dict[str, Any], source_dir: Path) -> None:
        normalized = plan if isinstance(plan, TaskPlan) else parse_plan(plan)
        if (self.task_root / normalized.task_id).exists():
            raise FileExistsError(f"task directory already exists: {normalized.task_id}")
        now = _now()
        try:
            self.db.execute(
                "INSERT INTO queue_task "
                "(task_id, plan_json, source_dir, state, created_at, updated_at) "
                "VALUES (?, ?, ?, 'queued', ?, ?)",
                (
                    normalized.task_id,
                    plan_json(normalized),
                    str(source_dir.expanduser().resolve()),
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"task is already queued: {normalized.task_id}") from exc
        self._event(normalized.task_id, "queued", {})
        self.db.commit()

    def claim_next(self) -> tuple[dict[str, Any] | None, bool]:
        self.db.execute("BEGIN IMMEDIATE")
        active = self.db.execute(
            "SELECT * FROM queue_task WHERE state = 'running' ORDER BY id LIMIT 1"
        ).fetchone()
        if active is not None and _pid_alive(active["runner_pid"]):
            self.db.commit()
            return None, True
        row = (
            active
            or self.db.execute(
                "SELECT * FROM queue_task WHERE state = 'queued' ORDER BY id LIMIT 1"
            ).fetchone()
        )
        if row is None:
            self.db.commit()
            return None, False
        task_id = str(row["task_id"])
        self.db.execute(
            "UPDATE queue_task SET state = 'running', runner_pid = ?, updated_at = ? "
            "WHERE task_id = ?",
            (os.getpid(), _now(), task_id),
        )
        self._event(task_id, "running", {"resume": row["state"] == "running"})
        claimed = self.db.execute(
            "SELECT * FROM queue_task WHERE task_id = ?", (task_id,)
        ).fetchone()
        self.db.commit()
        return dict(claimed), False

    def defer(self, task_id: str, reason: str, receipt_status: str = "WAITING") -> None:
        self._set_state(task_id, "queued", receipt_status, reason)

    def finish(
        self, task_id: str, state: str, receipt_status: str, reason: str | None = None
    ) -> None:
        if state not in {"done", "blocked"}:
            raise ValueError("queue task final state must be done or blocked")
        self._set_state(task_id, state, receipt_status, reason)

    def items(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT task_id, state, source_dir, receipt_status, last_error, created_at, updated_at "
            "FROM queue_task ORDER BY id"
        )
        return [dict(row) for row in rows]

    def _set_state(self, task_id: str, state: str, receipt_status: str, reason: str | None) -> None:
        self.db.execute(
            "UPDATE queue_task SET state = ?, runner_pid = NULL, receipt_status = ?, "
            "last_error = ?, updated_at = ? WHERE task_id = ?",
            (state, receipt_status, reason, _now(), task_id),
        )
        self._event(task_id, state, {"receipt_status": receipt_status, "reason": reason})
        self.db.commit()

    def _event(self, task_id: str, state: str, detail: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO queue_event (task_id, state, detail_json, created_at) VALUES (?, ?, ?, ?)",
            (task_id, state, json.dumps(detail, sort_keys=True), _now()),
        )


class OvernightQueue:
    """Run persisted queue entries serially through the existing arm service."""

    def __init__(self, task_root: Path, service: ArmService, gate: QueueGate) -> None:
        self.task_root = task_root
        self.service = service
        self.gate = gate
        self.service.bite_gate = gate.allows

    def run_next(self, *, override: bool = False) -> QueueRun:
        with QueueLedger(self.task_root) as ledger:
            item, active = ledger.claim_next()
        if item is None:
            return QueueRun("BUSY" if active else "EMPTY")
        task_id = str(item["task_id"])
        task_dir = self.task_root / task_id
        try:
            if task_dir.is_dir():
                result = self.service.resume(task_id, override=override)
            else:
                result = self.service.submit(
                    json.loads(item["plan_json"]), Path(item["source_dir"])
                )
            receipt_path = result / "receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            status = str(receipt["status"])
            with QueueLedger(self.task_root) as ledger:
                if status == "WAITING":
                    waiting_reason = (
                        self.gate.last_reason
                        or self.service.queue_yield_reason
                        or "task waits for approval"
                    )
                    ledger.defer(task_id, waiting_reason)
                    return QueueRun("WAITING", task_id, receipt_path, waiting_reason)
                final = "done" if status == "PASS" else "blocked"
                final_reason = None if status == "PASS" else f"task receipt status is {status}"
                ledger.finish(task_id, final, status, final_reason)
            return QueueRun(
                "DONE" if status == "PASS" else "BLOCKED", task_id, receipt_path, final_reason
            )
        except KeyboardInterrupt:
            with QueueLedger(self.task_root) as ledger:
                ledger.defer(task_id, "worker interrupted; task ledger will resume")
            raise
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            with QueueLedger(self.task_root) as ledger:
                ledger.finish(task_id, "blocked", "BLOCKED", reason)
            self._write_failure_receipt(task_id, task_dir, reason)
            return QueueRun("BLOCKED", task_id, task_dir / "receipt.json", reason)

    def _write_failure_receipt(self, task_id: str, task_dir: Path, reason: str) -> None:
        path = task_dir / "receipt.json"
        if path.is_file():
            return
        task_dir.mkdir(parents=True, exist_ok=True)
        receipt = {
            "head": self.service.build_sha,
            "utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "workdir": str(task_dir.resolve()),
            "task_id": task_id,
            "status": "BLOCKED",
            "error": reason,
            "results": [],
        }
        path.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8")


def _live_pids(path: Path) -> tuple[list[int], str | None]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return [], None
    except OSError as exc:
        return [], f"cannot read yield-lock PID file {path}: {exc}"
    pids = []
    for line in lines:
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid > 1 and _pid_alive(pid):
            pids.append(pid)
    return pids, None


def _pid_alive(value: Any) -> bool:
    if not isinstance(value, int) or value <= 1:
        return False
    try:
        os.kill(value, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _now() -> str:
    return datetime.now(UTC).isoformat()
