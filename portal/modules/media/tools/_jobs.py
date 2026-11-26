"""Shared async job manager and server-side long-poll helper for media MCP servers."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

_T = TypeVar("_T")

logger = logging.getLogger(__name__)

# A bare status poll stays short enough to return inside a normal chat turn.
DEFAULT_STATUS_WAIT_S = float(os.environ.get("MEDIA_STATUS_WAIT_S", "20.0"))
MAX_STATUS_WAIT_S = float(os.environ.get("MEDIA_STATUS_MAX_WAIT_S", "300.0"))
STATUS_TOOL_TIMEOUT_S = int(max(90, MAX_STATUS_WAIT_S + 30))
MAX_JOB_RECORDS = int(os.environ.get("MEDIA_MAX_JOB_RECORDS", "50"))
_TERMINAL_STATUSES = frozenset({"done", "error"})
# A status call waits this long past the job's own ETA before reporting "running".
ETA_SLACK_S = float(os.environ.get("MEDIA_JOB_ETA_SLACK_S", "30.0"))
# Quoted ETAs carry this margin over the measured EWMA duration.
ETA_MARGIN = float(os.environ.get("MEDIA_JOB_ETA_MARGIN", "1.25"))
EWMA_ALPHA = 0.3
DEFAULT_STATS_DIR = Path(
    os.environ.get("MEDIA_JOB_STATS_DIR", str(Path.home() / ".portal5" / "media"))
)


class JobDurationStats:
    """EWMA of measured successful job durations per eta key, persisted as JSON."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._entries: dict[str, dict[str, float]] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        if isinstance(raw, dict):
            self._entries = {key: value for key, value in raw.items() if isinstance(value, dict)}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._entries))
        except OSError:
            logger.warning("could not persist media job duration stats to %s", self.path)

    def observe(self, key: str, seconds: float) -> None:
        """Fold one measured successful duration into the key's EWMA."""
        if not key or seconds <= 0:
            return
        entry = self._entries.get(key)
        if entry is None:
            self._entries[key] = {"ewma_s": float(seconds), "samples": 1.0}
        else:
            previous = float(entry.get("ewma_s", seconds))
            entry["ewma_s"] = (1.0 - EWMA_ALPHA) * previous + EWMA_ALPHA * float(seconds)
            entry["samples"] = float(entry.get("samples", 0.0)) + 1.0
        self._save()

    def eta_s(self, key: str, default_s: float) -> float:
        """Measured ETA for the key (EWMA x margin), or the bootstrap default."""
        entry = self._entries.get(key)
        if not entry or float(entry.get("samples", 0.0)) < 1:
            return float(default_s)
        return round(float(entry.get("ewma_s", default_s)) * ETA_MARGIN, 1)


class MediaJobManager:
    """In-memory serialized job queue with server-side long-polling and idle release."""

    def __init__(
        self,
        *,
        max_jobs: int = MAX_JOB_RECORDS,
        default_wait_s: float = DEFAULT_STATUS_WAIT_S,
        max_wait_s: float = MAX_STATUS_WAIT_S,
        idle_timeout_s: float = 0.0,
        on_idle: Callable[[], Awaitable[Any] | Any] | None = None,
        stats: JobDurationStats | None = None,
    ) -> None:
        """Initialize the job queue, serialization lock, and optional idle callback."""
        self.max_jobs = max(1, int(max_jobs))
        self.default_wait_s = max(0.0, float(default_wait_s))
        self.max_wait_s = max(0.0, float(max_wait_s))
        self.idle_timeout_s = max(0.0, float(idle_timeout_s))
        self._on_idle = on_idle
        self._stats = stats
        self._jobs: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self._events: dict[str, asyncio.Event] = {}
        self._gen_lock = asyncio.Lock()
        self._active_count = 0
        self._idle_task: asyncio.Task[None] | None = None

    @property
    def is_busy(self) -> bool:
        """True when a generation job currently holds the serialization lock."""
        return self._gen_lock.locked()

    def cancel_idle_timer(self) -> None:
        """Cancel any pending idle-release timer."""
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = None

    def _schedule_idle_timer(self) -> None:
        """Arm an idle-release timer when no jobs remain active."""
        self.cancel_idle_timer()
        if self.idle_timeout_s <= 0 or self._on_idle is None or self._active_count > 0:
            return
        self._idle_task = asyncio.create_task(self._idle_waiter())

    async def _idle_waiter(self) -> None:
        try:
            await asyncio.sleep(self.idle_timeout_s)
            if self._active_count > 0 or self._gen_lock.locked() or self._on_idle is None:
                return
            res = self._on_idle()
            if inspect.isawaitable(res):
                await res
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Idle release callback failed")

    def notify_activity(self) -> None:
        """Reset the idle timer after synchronous or out-of-band model use."""
        if self._active_count == 0:
            self._schedule_idle_timer()

    def _record(self, job_id: str, **fields: Any) -> None:
        self._jobs.setdefault(job_id, {}).update(fields)

    def _new_job(self, initial: dict[str, Any]) -> str:
        job_id = uuid.uuid4().hex[:12]
        self._jobs[job_id] = initial
        self._events[job_id] = asyncio.Event()
        self._order.append(job_id)
        while len(self._order) > self.max_jobs:
            stale = self._order.pop(0)
            self._jobs.pop(stale, None)
            self._events.pop(stale, None)
        return job_id

    async def run_serialized(self, coro_factory: Callable[[], Awaitable[_T]]) -> _T:
        """Run a synchronous-facing job under the shared lock while keeping idle tracking accurate."""
        self.cancel_idle_timer()
        self._active_count += 1
        try:
            async with self._gen_lock:
                return await coro_factory()
        finally:
            self._active_count -= 1
            if self._active_count == 0:
                self._schedule_idle_timer()

    def start(
        self,
        runner: Callable[[Callable[[int, str], None]], Awaitable[dict[str, Any]]],
        *,
        initial_message: str = "Starting…",
        queued_message: str = "Queued behind another job…",
        extra_fields: dict[str, Any] | None = None,
        eta_key: str = "",
        eta_s: float | None = None,
    ) -> str:
        """Queue an async media job, return its job_id immediately, and notify on completion."""
        self.cancel_idle_timer()
        queued = self._gen_lock.locked()
        initial: dict[str, Any] = {
            "status": "queued" if queued else "running",
            "stage": 0,
            "message": queued_message if queued else initial_message,
            "created_at": time.time(),
        }
        if eta_key:
            initial["eta_key"] = eta_key
        if eta_s is not None and float(eta_s) > 0:
            initial["eta_s"] = round(float(eta_s), 1)
        if extra_fields:
            initial.update(extra_fields)
        job_id = self._new_job(initial)
        self._active_count += 1
        asyncio.create_task(self._execute(job_id, runner))
        return job_id

    async def _execute(
        self,
        job_id: str,
        runner: Callable[[Callable[[int, str], None]], Awaitable[dict[str, Any]]],
    ) -> None:
        def progress(stage: int, message: str) -> None:
            self._record(job_id, stage=stage, message=message)

        try:
            async with self._gen_lock:
                self._record(job_id, status="running", started_at=time.time())
                result = await runner(progress)
            if result.get("success"):
                fields = {**result, "status": "done", "finished_at": time.time()}
                fields.pop("error", None)
                url = fields.get("download_url") or fields.get("url")
                fields["message"] = f"Done. Return this download link: {url}" if url else "Done."
                self._record(job_id, **fields)
                self._jobs[job_id].pop("error", None)
                self._observe_duration(job_id)
            else:
                error = str(result.get("error", "unknown error"))
                self._record(
                    job_id,
                    status="error",
                    error=error,
                    message=f"Job failed: {error}",
                    next_action=(
                        "Report this failure to the user as stated; the job produced no "
                        "artifact and is not still running."
                    ),
                    finished_at=time.time(),
                )
        except Exception as exc:
            logger.exception("Media job %s failed", job_id)
            self._record(
                job_id,
                status="error",
                error=str(exc),
                message=f"Job failed: {exc}",
                next_action=(
                    "Report this failure to the user as stated; the job produced no "
                    "artifact and is not still running."
                ),
                finished_at=time.time(),
            )
        finally:
            event = self._events.get(job_id)
            if event is not None:
                event.set()
            self._active_count -= 1
            if self._active_count == 0:
                self._schedule_idle_timer()

    def _observe_duration(self, job_id: str) -> None:
        """Fold one successful job's measured duration into the ETA statistics."""
        job = self._jobs.get(job_id, {})
        key = str(job.get("eta_key") or "")
        started = job.get("started_at")
        finished = job.get("finished_at")
        if self._stats is None or not key or not isinstance(started, (int, float)):
            return
        end = finished if isinstance(finished, (int, float)) else time.time()
        self._stats.observe(key, float(end) - float(started))

    async def status(self, job_id: str, wait_s: float | None = None) -> dict[str, Any]:
        """Long-poll up to a bounded wait and return job progress or the finished result."""
        job = self._jobs.get(job_id)
        if job is None:
            return {
                "status": "unknown",
                "job_id": job_id,
                "message": "No such job (or it aged out).",
            }
        raw_wait = self.default_wait_s if wait_s is None else float(wait_s)
        bounded = min(max(raw_wait, 0.0), self.max_wait_s)
        event = self._events.get(job_id)
        if job.get("status") not in _TERMINAL_STATUSES:
            bounded = min(max(bounded, self._eta_wait_s(job)), self.max_wait_s)
        if job.get("status") not in _TERMINAL_STATUSES and bounded > 0 and event is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(event.wait(), timeout=bounded)
        snapshot = dict(self._jobs.get(job_id, job))
        now = snapshot.get("finished_at") or time.time()
        created = snapshot.get("created_at")
        if isinstance(created, (int, float)):
            snapshot["elapsed_s"] = round(max(0.0, float(now) - float(created)), 2)
        if snapshot.get("status") not in _TERMINAL_STATUSES:
            snapshot["next_action"] = _running_next_action(snapshot)
        return {"job_id": job_id, **snapshot}

    def _eta_wait_s(self, job: dict[str, Any]) -> float:
        """Extra wait so one status call made near the ETA returns the finished job."""
        eta = job.get("eta_s")
        if not isinstance(eta, (int, float)) or float(eta) <= 0:
            return 0.0
        base = job.get("started_at") or job.get("created_at")
        if not isinstance(base, (int, float)):
            return 0.0
        return float(base) + float(eta) + ETA_SLACK_S - time.time()


def _running_next_action(snapshot: dict[str, Any]) -> str:
    base = snapshot.get("started_at") or snapshot.get("created_at")
    eta = snapshot.get("eta_s")
    hint = ""
    if isinstance(base, (int, float)) and isinstance(eta, (int, float)) and float(eta) > 0:
        remaining = max(0.0, float(base) + float(eta) - time.time())
        snapshot["eta_remaining_s"] = round(remaining, 1)
        hint = f", expected to finish in about {int(remaining)}s"
    return (
        f"Still running{hint}. Report this progress and poll again in a later turn to "
        "retrieve the download link."
    )


def start_reply(job_id: str, status_tool: str, note: str, **extra: Any) -> dict[str, Any]:
    """Standard fast reply payload returned by media *_start tools."""
    eta_s = extra.pop("eta_s", None)
    eta = round(float(eta_s)) if isinstance(eta_s, (int, float)) and float(eta_s) > 0 else 0
    reply: dict[str, Any] = {
        "success": True,
        "job_id": job_id,
        "status": extra.pop("status", "running"),
    }
    if eta:
        reply["eta_s"] = eta
    reply["next_action"] = f"in a later turn, call {status_tool} with job_id='{job_id}'"
    if eta:
        minutes = max(1, round(eta / 60))
        reply["message"] = (
            f"Generation started (job {job_id}; {note}). The job continues asynchronously "
            f"and should finish in about {eta}s (~{minutes} min). Return the job id and this "
            f"ETA now. In a later turn, once that time has passed, call {status_tool} with "
            f"job_id='{job_id}' once: it waits for the job and returns the download link when "
            "it is done. If it is still running, report the progress and ask the user to "
            "check again later. Do not poll in this turn."
        )
    else:
        reply["message"] = (
            f"Generation started (job {job_id}; {note}). The job continues asynchronously. "
            "Return the job id now. In a later turn, call "
            f"{status_tool}(job_id='{job_id}', wait_s=20) to check progress or retrieve the "
            "download link. If still running, report the progress and ask the user to check "
            "again later. Do not poll in this turn."
        )
    reply.update(extra)
    return reply
