"""Persistent single-worker queue for unattended orchestration tasks."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import Bite, TaskPlan, plan_json
from .jobs import (
    JobNoticeSink,
    JobRunner,
    JobSpec,
    _ps_process_details,
    job_json,
    parse_job_spec,
)
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

    def external_reason(self) -> str | None:
        """The host-quiet reason a job also has to respect."""
        return self._external_lock_reason()

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
                kind TEXT NOT NULL DEFAULT 'plan',
                plan_json TEXT NOT NULL,
                source_dir TEXT NOT NULL,
                state TEXT NOT NULL,
                runner_pid INTEGER,
                runner_started TEXT,
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
        self._migrate_kind()
        self.db.commit()

    def _migrate_kind(self) -> None:
        columns = {str(row[1]) for row in self.db.execute("PRAGMA table_info(queue_task)")}
        if "kind" not in columns:
            self.db.execute("ALTER TABLE queue_task ADD COLUMN kind TEXT NOT NULL DEFAULT 'plan'")
        if "runner_started" not in columns:
            self.db.execute("ALTER TABLE queue_task ADD COLUMN runner_started TEXT")

    def __enter__(self) -> QueueLedger:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.db.close()

    def enqueue(self, plan: TaskPlan, source_dir: Path) -> None:
        if not isinstance(plan, TaskPlan) or not plan.policy_validated:
            raise TypeError("queue plans must be policy-validated TaskPlan objects")
        normalized = plan
        if (self.task_root / normalized.task_id).exists():
            raise FileExistsError(f"task directory already exists: {normalized.task_id}")
        self._insert(normalized.task_id, "plan", plan_json(normalized), source_dir)
        self._event(normalized.task_id, "queued", {})
        self.db.commit()

    def enqueue_job(self, spec: JobSpec, source_dir: Path) -> None:
        if not isinstance(spec, JobSpec):
            raise TypeError("queue jobs must be validated JobSpec objects")
        task_dir = self.task_root / spec.job_id
        if task_dir.exists():
            raise FileExistsError(f"task directory already exists: {spec.job_id}")
        task_dir.mkdir(parents=True)
        try:
            (task_dir / "job.json").write_text(
                json.dumps(spec.as_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8"
            )
            self._insert(spec.job_id, "job", job_json(spec), source_dir.expanduser().resolve())
        except Exception:
            shutil.rmtree(task_dir, ignore_errors=True)
            raise
        self._event(spec.job_id, "queued", {"kind": "job"})
        self.db.commit()

    def _insert(self, task_id: str, kind: str, plan: str, source_dir: Path) -> None:
        now = _now()
        try:
            self.db.execute(
                "INSERT INTO queue_task "
                "(task_id, kind, plan_json, source_dir, state, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'queued', ?, ?)",
                (task_id, kind, plan, str(source_dir), now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"task is already queued: {task_id}") from exc

    def claim_next(self) -> tuple[dict[str, Any] | None, bool]:
        self.db.execute("BEGIN IMMEDIATE")
        active = self.db.execute(
            "SELECT * FROM queue_task WHERE state = 'running' ORDER BY id LIMIT 1"
        ).fetchone()
        if active is not None and _runner_alive(active["runner_pid"], active["runner_started"]):
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
        identity = _ps_process_details(os.getpid())
        runner_started = identity[0] if identity else None
        self.db.execute(
            "UPDATE queue_task SET state = 'running', runner_pid = ?, runner_started = ?, "
            "updated_at = ? "
            "WHERE task_id = ?",
            (os.getpid(), runner_started, _now(), task_id),
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

    def task(self, task_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM queue_task WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row is not None else None

    def active_other(self, task_id: str) -> str | None:
        row = self.db.execute(
            "SELECT task_id, runner_pid, runner_started FROM queue_task "
            "WHERE state = 'running' AND task_id != ? ORDER BY id LIMIT 1",
            (task_id,),
        ).fetchone()
        if row is None or not _runner_alive(row["runner_pid"], row["runner_started"]):
            return None
        return f"queue task {row['task_id']} is running (pid {row['runner_pid']})"

    def requeue(self, task_id: str) -> None:
        self.db.execute(
            "UPDATE queue_task SET state = 'queued', runner_pid = NULL, runner_started = NULL, "
            "receipt_status = NULL, "
            "last_error = NULL, updated_at = ? WHERE task_id = ?",
            (_now(), task_id),
        )
        self._event(task_id, "queued", {"requeue": True})
        self.db.commit()

    def cancel_task(self, task_id: str, reason: str, *, force: bool = False) -> None:
        """Queued becomes blocked/CANCELLED. A live runner is refused unless force and the pid is dead."""
        text = reason.strip() or "cancelled by operator"
        self._assert_cancellable(task_id, force=force)
        self._backup_db()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._assert_cancellable(task_id, force=force)
            self._set_state_in_txn(task_id, "blocked", "CANCELLED", text)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def requeue_job(self, task_id: str, plan: str) -> None:
        """Blocked or done job returns to queued with the spec re-read by the caller."""
        self._assert_requeue_job(task_id)
        self._backup_db()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._assert_requeue_job(task_id)
            now = _now()
            self.db.execute(
                "UPDATE queue_task SET state = 'queued', plan_json = ?, runner_pid = NULL, "
                "runner_started = NULL, "
                "receipt_status = NULL, last_error = NULL, updated_at = ? WHERE task_id = ?",
                (plan, now, task_id),
            )
            self._event(task_id, "queued", {"requeue": True})
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _assert_cancellable(self, task_id: str, *, force: bool) -> None:
        row = self.db.execute(
            "SELECT state, runner_pid, runner_started FROM queue_task WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"no queue task: {task_id}")
        _require_cancellable(
            task_id, str(row["state"]), row["runner_pid"], row["runner_started"], force=force
        )

    def _assert_requeue_job(self, task_id: str) -> None:
        row = self.db.execute(
            "SELECT kind, state FROM queue_task WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"no queue task: {task_id}")
        if str(row["kind"]) != "job":
            raise ValueError(f"queue task {task_id} is not a job")
        if str(row["state"]) not in {"blocked", "done"}:
            raise ValueError(
                f"queue task {task_id} is {row['state']}; requeue accepts blocked or done"
            )

    def _backup_db(self) -> Path:
        # backup() on a connection that is inside a transaction sleeps in sqlite3_sleep.
        self.db.rollback()
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        dest = self.task_root / f"queue.sqlite3.{stamp}.bak"
        if dest.exists():
            dest = self.task_root / f"queue.sqlite3.{stamp}.{os.getpid()}.bak"
        source = sqlite3.connect(self.task_root / "queue.sqlite3")
        target = sqlite3.connect(dest)
        try:
            source.backup(target)
        except Exception:
            target.close()
            source.close()
            dest.unlink(missing_ok=True)
            raise
        target.close()
        source.close()
        return dest

    def _set_state_in_txn(self, task_id: str, state: str, receipt_status: str, reason: str) -> None:
        self.db.execute(
            "UPDATE queue_task SET state = ?, runner_pid = NULL, runner_started = NULL, "
            "receipt_status = ?, "
            "last_error = ?, updated_at = ? WHERE task_id = ?",
            (state, receipt_status, reason, _now(), task_id),
        )
        self._event(task_id, state, {"receipt_status": receipt_status, "reason": reason})

    def items(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT task_id, kind, state, source_dir, receipt_status, last_error, "
            "created_at, updated_at FROM queue_task ORDER BY id"
        )
        return [dict(row) for row in rows]

    def _set_state(self, task_id: str, state: str, receipt_status: str, reason: str | None) -> None:
        self.db.execute(
            "UPDATE queue_task SET state = ?, runner_pid = NULL, runner_started = NULL, "
            "receipt_status = ?, "
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
    """Run persisted queue entries serially through the arm service or a job runner."""

    def __init__(
        self,
        task_root: Path,
        service: ArmService | None,
        gate: QueueGate,
        *,
        repo_root: Path | None = None,
        notices: JobNoticeSink | None = None,
        job_factory: Callable[[], JobRunner] | None = None,
    ) -> None:
        self.task_root = task_root
        self.service = service
        self.gate = gate
        self.repo_root = repo_root or Path(__file__).resolve().parents[3]
        self.notices = notices or (service.notices if service is not None else None)
        self.job_factory = job_factory
        if service is not None:
            service.bite_gate = gate.allows

    def run_next(self, *, override: bool = False) -> QueueRun:
        with QueueLedger(self.task_root) as ledger:
            item, active = ledger.claim_next()
        if item is None:
            return QueueRun("BUSY" if active else "EMPTY")
        task_id = str(item["task_id"])
        task_dir = self.task_root / task_id
        try:
            if item.get("kind") == "job":
                return self._run_job(item)
            if self.service is None:
                raise RuntimeError(
                    "plan task needs the arm service; set PIPELINE_API_KEY and seat digests"
                )
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

    def _run_job(self, item: dict[str, Any]) -> QueueRun:
        job_id = str(item["task_id"])
        # A job runs from the checkout it was enqueued from (a pinned snapshot stays pinned).
        source = Path(item["source_dir"]) if item.get("source_dir") else self.repo_root
        root = source if source.is_dir() else self.repo_root
        spec = parse_job_spec(json.loads(item["plan_json"]), repo_root=root)
        runner = (
            self.job_factory()
            if self.job_factory is not None
            else JobRunner(
                self.task_root,
                repo_root=root,
                gate=self.gate,
                notices=self.notices,
            )
        )
        result = runner.run(spec)
        with QueueLedger(self.task_root) as ledger:
            if result.status == "WAITING":
                reason = result.reason or "job waits for precondition clearance"
                ledger.defer(job_id, reason)
                return QueueRun("WAITING", job_id, result.receipt_path, reason)
            final = "done" if result.status == "PASS" else "blocked"
            final_reason = (
                None
                if result.status == "PASS"
                else f"job receipt status is {result.status}: {result.reason}"
            )
            ledger.finish(job_id, final, result.status, final_reason)
        return QueueRun(
            "DONE" if result.status == "PASS" else "BLOCKED",
            job_id,
            result.receipt_path,
            final_reason,
        )

    def _write_failure_receipt(self, task_id: str, task_dir: Path, reason: str) -> None:
        path = task_dir / "receipt.json"
        if path.is_file():
            return
        task_dir.mkdir(parents=True, exist_ok=True)
        receipt = {
            "head": self.service.build_sha if self.service is not None else "unknown",
            "utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "workdir": str(task_dir.resolve()),
            "task_id": task_id,
            "status": "BLOCKED",
            "error": reason,
            "results": [],
        }
        path.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8")


def _require_cancellable(
    task_id: str, state: str, runner_pid: Any, runner_started: Any, *, force: bool
) -> None:
    if state == "queued":
        return
    if state != "running":
        raise ValueError(f"queue task {task_id} is {state}; only a queued task can be cancelled")
    if not force:
        raise ValueError(f"queue task {task_id} is running; pass --force when its runner is dead")
    if _runner_alive(runner_pid, runner_started):
        raise ValueError(f"queue task {task_id} runner is still alive (pid {runner_pid})")


def _runner_alive(pid: Any, started: Any) -> bool:
    if not _pid_alive(pid):
        return False
    if not isinstance(started, str) or not started.strip():
        return True
    details = _ps_process_details(pid)
    return details is None or (details[0] == started and not details[1].startswith("Z"))


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
