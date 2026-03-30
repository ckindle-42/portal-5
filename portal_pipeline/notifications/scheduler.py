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

        # Import SummaryEvent here to avoid circular import
        from portal_pipeline.notifications.events import SummaryEvent

        event = SummaryEvent(
            timestamp=now,
            total_requests=total,
            requests_by_workspace=dict(_request_count),
            healthy_backends=healthy,
            total_backends=total_backends,
            uptime_seconds=now.timestamp() - _startup_time if _startup_time else 0.0,
        )

        await _registry_ref.dispatch(event)
        logger.info(
            "Daily summary dispatched: %d requests across %d workspaces",
            total,
            len(_request_count),
        )
