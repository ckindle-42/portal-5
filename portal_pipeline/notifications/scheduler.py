"""Portal 5 — Notification scheduler for daily usage summaries."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    AsyncIOScheduler = None  # type: ignore[assignment, misc]
    CronTrigger = None  # type: ignore[assignment, misc]

if TYPE_CHECKING:
    from portal_pipeline.cluster_backends import BackendRegistry
    from portal_pipeline.notifications.dispatcher import NotificationDispatcher

logger = logging.getLogger(__name__)

# Cooldown file: prevents duplicate sends when PIPELINE_WORKERS > 1.
# All uvicorn workers share /tmp (in-memory tmpfs), so they coordinate via this file.
_COOLDOWN_FILE = Path("/tmp/.portal_daily_summary_sent")
_COOLDOWN_SECONDS = 23 * 3600  # 23 hours — staggered send on restart is fine

# Snapshot file: stores previous-day metrics so the summary shows deltas, not totals.
_SNAPSHOT_FILE = Path("/tmp/.portal_daily_summary_snapshot.json")

# Module-level references to router_pipe state (set during integration)
_request_count: dict[str, int] = {}
_startup_time: float = 0.0
_registry_ref: NotificationDispatcher | None = None
_registry_instance: BackendRegistry | None = None


def _attach_to_pipeline(
    dispatcher: NotificationDispatcher,
    request_count: dict[str, int],
    startup_time: float,
    registry: BackendRegistry | None = None,
) -> None:
    """
    Called during router_pipe lifespan startup to attach scheduler
    to the pipeline's module-level metrics state.

    Note: Extended stats (TPS, response time, tokens, model usage) are read
    directly from router_pipe module at send time via getattr(), avoiding
    stale closure issues with scalar values.
    """
    global _registry_ref, _request_count, _startup_time, _registry_instance
    _registry_ref = dispatcher
    _request_count = request_count
    _startup_time = startup_time
    _registry_instance = registry
    logger.info("NotificationScheduler attached to pipeline metrics")


def _load_snapshot() -> dict[str, Any]:
    """Load previous-day metrics snapshot from disk."""
    try:
        if _SNAPSHOT_FILE.exists():
            return json.loads(_SNAPSHOT_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_snapshot(metrics: dict[str, Any]) -> None:
    """Save current metrics snapshot to disk for next-day delta computation."""
    try:
        _SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SNAPSHOT_FILE.write_text(json.dumps(metrics, default=str))
    except OSError:
        pass


def _delta(current: int | float, previous: int | float) -> int | float:
    """Compute delta, clamping to zero if counter was reset."""
    diff = current - previous
    return max(diff, 0) if isinstance(diff, (int, float)) else 0


def _delta_dict(current: dict[str, int], previous: dict[str, int]) -> dict[str, int]:
    """Compute per-key delta between two count dicts."""
    result: dict[str, int] = {}
    for key, val in current.items():
        d = val - previous.get(key, 0)
        if d > 0:
            result[key] = d
    return result


class NotificationScheduler:
    """
    APScheduler-based daily summary trigger.

    Fires a SummaryEvent at a configured hour (default: 09:00 UTC) each day,
    pulling request counts and backend health from the pipeline's live state.
    Gracefully degrades if APScheduler is not installed.
    """

    def __init__(self, dispatcher: NotificationDispatcher) -> None:
        self._dispatcher = dispatcher
        self._scheduler = AsyncIOScheduler() if APSCHEDULER_AVAILABLE else None
        self._enabled = APSCHEDULER_AVAILABLE and os.environ.get(
            "ALERT_SUMMARY_ENABLED", "true"
        ).lower() in ("true", "1", "yes")

    def start(self) -> None:
        if not self._enabled:
            if not APSCHEDULER_AVAILABLE:
                logger.info(
                    "NotificationScheduler: APScheduler not installed — daily summaries disabled"
                )
            else:
                logger.info("NotificationScheduler: daily summaries disabled via env")
            return

        hour = int(os.environ.get("ALERT_SUMMARY_HOUR", "9"))
        timezone = os.environ.get("ALERT_SUMMARY_TIMEZONE", "UTC")

        self._scheduler.add_job(  # type: ignore[union-attr]
            self._send_daily_summary,
            CronTrigger(hour=hour, minute=0, timezone=timezone),
            id="daily_summary",
            replace_existing=True,
        )
        self._scheduler.start()  # type: ignore[union-attr]
        logger.info(
            "NotificationScheduler: daily summary scheduled at %02d:00 %s",
            hour,
            timezone,
        )

    def stop(self) -> None:
        if self._scheduler is not None and self._scheduler.running:  # type: ignore[union-attr]
            self._scheduler.shutdown(wait=False)  # type: ignore[union-attr]
            logger.info("NotificationScheduler: stopped")

    async def _send_daily_summary(self) -> None:
        """Build and dispatch a daily summary from live pipeline metrics.

        Computes deltas against the previous day's snapshot so the summary
        shows only yesterday's activity, not cumulative totals since startup.
        """
        if _registry_ref is None:
            logger.warning("NotificationScheduler: dispatcher not attached")
            return

        # Cooldown check: all uvicorn workers share /tmp, so this prevents
        # duplicate sends when PIPELINE_WORKERS > 1 (all workers fire at the
        # same cron moment; only the first to write the lockfile proceeds).
        now_ts = time.time()
        try:
            if _COOLDOWN_FILE.exists():
                last_sent = float(_COOLDOWN_FILE.read_text().strip())
                if now_ts - last_sent < _COOLDOWN_SECONDS:
                    logger.debug(
                        "Daily summary skipped: sent %.1f hours ago (cooldown active)",
                        (now_ts - last_sent) / 3600,
                    )
                    return
        except (ValueError, OSError):
            pass

        # First to acquire the lock writes its timestamp; others see it and skip.
        # Atomic-ish on POSIX: unlink+write is safe for our purposes.
        try:
            _COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
            _COOLDOWN_FILE.write_text(str(int(now_ts)))
        except OSError:
            pass

        # Read current stats directly from router_pipe module (avoids stale closures)
        from portal_pipeline import router_pipe

        now = datetime.now(timezone.utc)
        report_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")

        # Snapshot current cumulative metrics
        healthy = 0
        total_backends = 0

        if _registry_instance is not None:
            try:
                total_backends = len(_registry_instance._backends)
                healthy = len([b for b in _registry_instance._backends.values() if b.healthy])
            except Exception:
                pass

        current_snapshot: dict[str, Any] = {
            "request_count": dict(_request_count),
            "total_response_time_ms": getattr(router_pipe, "_total_response_time_ms", 0.0),
            "total_tps": getattr(router_pipe, "_total_tps", 0.0),
            "request_tps_count": getattr(router_pipe, "_request_tps_count", 0),
            "total_input_tokens": getattr(router_pipe, "_total_input_tokens", 0),
            "total_output_tokens": getattr(router_pipe, "_total_output_tokens", 0),
            "req_count_by_model": dict(getattr(router_pipe, "_req_count_by_model", {})),
            "req_count_by_error": dict(getattr(router_pipe, "_req_count_by_error", {})),
            "peak_concurrent": getattr(router_pipe, "_peak_concurrent", 0),
        }

        # Load previous snapshot and compute deltas
        prev = _load_snapshot()

        prev_request_count: dict[str, int] = prev.get("request_count", {})
        prev_rt_ms: float = float(prev.get("total_response_time_ms", 0.0))
        prev_tps_sum: float = float(prev.get("total_tps", 0.0))
        prev_tps_count: int = int(prev.get("request_tps_count", 0))
        prev_inp: int = int(prev.get("total_input_tokens", 0))
        prev_out: int = int(prev.get("total_output_tokens", 0))
        prev_by_model: dict[str, int] = prev.get("req_count_by_model", {})
        prev_by_error: dict[str, int] = prev.get("req_count_by_error", {})

        daily_requests = _delta_dict(dict(_request_count), prev_request_count)
        daily_total = sum(daily_requests.values())
        daily_rt_ms = _delta(getattr(router_pipe, "_total_response_time_ms", 0.0), prev_rt_ms)
        daily_tps_sum = _delta(getattr(router_pipe, "_total_tps", 0.0), prev_tps_sum)
        daily_tps_count = _delta(getattr(router_pipe, "_request_tps_count", 0), prev_tps_count)
        daily_inp = _delta(getattr(router_pipe, "_total_input_tokens", 0), prev_inp)
        daily_out = _delta(getattr(router_pipe, "_total_output_tokens", 0), prev_out)
        daily_by_model = _delta_dict(
            dict(getattr(router_pipe, "_req_count_by_model", {})), prev_by_model
        )
        daily_by_error = _delta_dict(
            dict(getattr(router_pipe, "_req_count_by_error", {})), prev_by_error
        )

        # Read persona usage (Prometheus Counter — compute delta via scrape)
        persona_usage: dict[str, int] = {}
        try:
            persona_counter = getattr(router_pipe, "_persona_usage", None)
            if persona_counter is not None:
                for sample in persona_counter._metrics.values():
                    for (labels,), value in sample.items():
                        persona = labels.get("persona", "unknown")
                        count = int(value)
                        persona_usage[persona] = persona_usage.get(persona, 0) + count
        except Exception:
            pass

        # Compute derived metrics from daily deltas
        avg_tps = daily_tps_sum / daily_tps_count if daily_tps_count > 0 else 0.0
        avg_response_ms = daily_rt_ms / daily_total if daily_total > 0 else 0.0

        # Import SummaryEvent here to avoid circular import
        from portal_pipeline.notifications.events import SummaryEvent

        event = SummaryEvent(
            timestamp=now,
            report_date=report_date,
            total_requests=daily_total,
            requests_by_workspace=daily_requests,
            healthy_backends=healthy,
            total_backends=total_backends,
            uptime_seconds=now.timestamp() - _startup_time if _startup_time else 0.0,
            # Extended metrics
            requests_by_model=daily_by_model,
            avg_tokens_per_second=avg_tps,
            total_input_tokens=daily_inp,
            total_output_tokens=daily_out,
            avg_response_time_ms=avg_response_ms,
            # Error metrics
            errors_by_type=daily_by_error,
            total_errors=sum(daily_by_error.values()),
            peak_concurrent=current_snapshot["peak_concurrent"],
            persona_usage=persona_usage,
        )

        await _registry_ref.dispatch(event)

        # Save current snapshot for tomorrow's delta computation
        _save_snapshot(current_snapshot)

        logger.info(
            "Daily summary dispatched for %s: %d requests across %d workspaces, "
            "avg TPS=%.1f, avg response=%.0fms",
            report_date,
            daily_total,
            len(daily_requests),
            avg_tps,
            avg_response_ms,
        )
