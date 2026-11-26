"""Shared async job manager and server-side long-poll helper for media MCP servers."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

_T = TypeVar("_T")

logger = logging.getLogger(__name__)

# A bare status poll stays short enough to return inside a normal chat turn.
DEFAULT_STATUS_WAIT_S = float(os.environ.get("MEDIA_STATUS_WAIT_S", "20.0"))
MAX_STATUS_WAIT_S = float(os.environ.get("MEDIA_STATUS_MAX_WAIT_S", "300.0"))
STATUS_TOOL_TIMEOUT_S = int(max(90, MAX_STATUS_WAIT_S + 30))
MAX_JOB_RECORDS = int(os.environ.get("MEDIA_MAX_JOB_RECORDS", "50"))
_TERMINAL_STATUSES = frozenset({"done", "error"})


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
    ) -> None:
        """Initialize the job queue, serialization lock, and optional idle callback."""
        self.max_jobs = max(1, int(max_jobs))
        self.default_wait_s = max(0.0, float(default_wait_s))
        self.max_wait_s = max(0.0, float(max_wait_s))
        self.idle_timeout_s = max(0.0, float(idle_timeout_s))
        self._on_idle = on_idle
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
            else:
                self._record(
                    job_id,
                    status="error",
                    error=result.get("error", "unknown error"),
                    finished_at=time.time(),
                )
        except Exception as exc:
            logger.exception("Media job %s failed", job_id)
            self._record(job_id, status="error", error=str(exc), finished_at=time.time())
        finally:
            event = self._events.get(job_id)
            if event is not None:
                event.set()
            self._active_count -= 1
            if self._active_count == 0:
                self._schedule_idle_timer()

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
        if job.get("status") not in _TERMINAL_STATUSES and bounded > 0 and event is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(event.wait(), timeout=bounded)
        snapshot = dict(self._jobs.get(job_id, job))
        now = snapshot.get("finished_at") or time.time()
        created = snapshot.get("created_at")
        if isinstance(created, (int, float)):
            snapshot["elapsed_s"] = round(max(0.0, float(now) - float(created)), 2)
        if snapshot.get("status") not in _TERMINAL_STATUSES:
            snapshot["next_action"] = (
                "Still running. Report this progress and poll again in a later turn to retrieve "
                "the download link."
            )
        return {"job_id": job_id, **snapshot}


def start_reply(job_id: str, status_tool: str, note: str, **extra: Any) -> dict[str, Any]:
    """Standard fast reply payload returned by media *_start tools."""
    return {
        "success": True,
        "job_id": job_id,
        "status": extra.pop("status", "running"),
        "next_action": f"in a later turn, call {status_tool} with job_id='{job_id}'",
        "message": (
            f"Generation started (job {job_id}; {note}). The job continues asynchronously. "
            "Return the job id now. In a later turn, call "
            f"{status_tool}(job_id='{job_id}', wait_s=20) to check progress or retrieve the "
            "download link. If still running, report the progress and ask the user to check "
            "again later. Do not poll in this turn."
        ),
        **extra,
    }
