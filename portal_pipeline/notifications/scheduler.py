"""Portal 5 — Notification scheduler for daily usage summaries."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING

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
        """Build and dispatch a daily summary from live pipeline metrics."""
        if _registry_ref is None:
            logger.warning("NotificationScheduler: dispatcher not attached")
            return

        # Read current stats directly from router_pipe module (avoids stale closures)
        from portal_pipeline import router_pipe

        now = datetime.utcnow()
        total = sum(_request_count.values())
        healthy = 0
        total_backends = 0

        if _registry_instance is not None:
            try:
                total_backends = len(_registry_instance._backends)
                healthy = len([b for b in _registry_instance._backends.values() if b.healthy])
            except Exception:
                pass

        # Read extended stats from router_pipe module directly at send time
        # This ensures we get the current values, not stale copies
        rt_ms = getattr(router_pipe, "_total_response_time_ms", 0.0)
        rt_count = total  # Use total requests as denominator for response time
        tps_sum = getattr(router_pipe, "_total_tps", 0.0)
        tps_count = getattr(router_pipe, "_request_tps_count", 0)
        inp_tokens = getattr(router_pipe, "_total_input_tokens", 0)
        out_tokens = getattr(router_pipe, "_total_output_tokens", 0)
        req_by_model: dict = getattr(router_pipe, "_req_count_by_model", {})

        # Compute derived metrics from running totals
        avg_tps = tps_sum / tps_count if tps_count > 0 else 0.0
        avg_response_ms = rt_ms / rt_count if rt_count > 0 else 0.0

        # Import SummaryEvent here to avoid circular import
        from portal_pipeline.notifications.events import SummaryEvent

        event = SummaryEvent(
            timestamp=now,
            total_requests=total,
            requests_by_workspace=dict(_request_count),
            healthy_backends=healthy,
            total_backends=total_backends,
            uptime_seconds=now.timestamp() - _startup_time if _startup_time else 0.0,
            # Extended metrics
            requests_by_model=dict(req_by_model),
            avg_tokens_per_second=avg_tps,
            total_input_tokens=inp_tokens,
            total_output_tokens=out_tokens,
            avg_response_time_ms=avg_response_ms,
        )

        await _registry_ref.dispatch(event)
        logger.info(
            "Daily summary dispatched: %d requests across %d workspaces, "
            "avg TPS=%.1f, avg response=%.0fms",
            total,
            len(_request_count),
            avg_tps,
            avg_response_ms,
        )
