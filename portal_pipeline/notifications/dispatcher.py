"""Portal 5 — Notification dispatcher: fans out events to all configured channels."""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from portal_pipeline.cluster_backends import BackendRegistry
    from portal_pipeline.notifications.channels import NotificationChannel
    from portal_pipeline.notifications.events import AlertEvent, SummaryEvent
else:
    # Late imports to avoid circular dependency at runtime
    from portal_pipeline.notifications.events import AlertEvent, EventType

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """
    Unified event bus for Portal 5 notifications.

    Tracks consecutive failure counts per backend for threshold-based alerting.
    On state transitions (backend down → recovered, all healthy → all down),
    fires AlertEvent to all configured channels asynchronously.
    """

    def __init__(self) -> None:
        self._channels: list[NotificationChannel] = []
        # Tracks consecutive failure count per backend_id
        self._failure_counts: dict[str, int] = defaultdict(int)
        # Debounce: prevent spamming "all down" alerts until state changes
        self._alerted_all_down = False
        self._enabled = os.environ.get("NOTIFICATIONS_ENABLED", "false").lower() in (
            "true",
            "1",
            "yes",
        )

    def add_channel(self, channel: NotificationChannel) -> None:
        if not self._enabled:
            return
        self._channels.append(channel)
        logger.info("Notification channel registered: %s", channel.name)

    def _schedule(self, coro) -> None:
        """Schedule a coroutine — prefer background task, fall back to sync execution."""
        try:
            asyncio.ensure_future(coro)
        except RuntimeError:
            # No running event loop (e.g., in tests) — run synchronously
            import asyncio as _asyncio

            _asyncio.run(coro)

    async def dispatch(self, event: AlertEvent | SummaryEvent) -> None:
        """Fan out an event to all registered channels, fire-and-forget."""
        if not self._enabled or not self._channels:
            return

        # Dispatch concurrently to all channels
        tasks = [channel.send(event) for channel in self._channels]
        await asyncio.gather(*tasks, return_exceptions=True)

    # ── Threshold checking ──────────────────────────────────────────────────

    def check_thresholds_and_alert(
        self,
        registry: BackendRegistry,
        down_threshold: int | None = None,
        alert_all_down: bool = True,
    ) -> None:
        """
        Called after each health check cycle.
        Checks per-backend failure counts and fires events on state transitions.

        Args:
            registry: The BackendRegistry with current health state
            down_threshold: Consecutive failures before firing BACKEND_DOWN (default: 3)
            alert_all_down: Whether to fire ALL_BACKENDS_DOWN event
        """
        if down_threshold is None:
            down_threshold = int(os.environ.get("ALERT_BACKEND_DOWN_THRESHOLD", "3"))

        all_backend_ids = set(registry._backends.keys())
        currently_healthy: set[str] = set()

        for backend_id, backend in registry._backends.items():
            if backend.healthy:
                currently_healthy.add(backend_id)
                # State transition: was failing, now healthy
                if self._failure_counts.get(backend_id, 0) >= down_threshold:
                    self._failure_counts[backend_id] = 0
                    event = AlertEvent(
                        type=EventType.BACKEND_RECOVERED,
                        message=f"Backend '{backend_id}' is healthy again.",
                        backend_id=backend_id,
                    )
                    self._schedule(self.dispatch(event))
                    logger.info("Backend recovered: %s", backend_id)
                else:
                    self._failure_counts[backend_id] = 0
            else:
                self._failure_counts[backend_id] += 1
                count = self._failure_counts[backend_id]
                # State transition: crossed threshold
                if count == down_threshold:
                    event = AlertEvent(
                        type=EventType.BACKEND_DOWN,
                        message=(
                            f"Backend '{backend_id}' has been unhealthy for "
                            f"{down_threshold} consecutive checks."
                        ),
                        backend_id=backend_id,
                    )
                    self._schedule(self.dispatch(event))
                    logger.warning("Backend down threshold reached: %s", backend_id)

        # All-backends-down event (debounced — fire once, not every cycle)
        if (
            alert_all_down
            and not currently_healthy
            and all_backend_ids
            and not self._alerted_all_down
        ):
            self._alerted_all_down = True
            event = AlertEvent(
                type=EventType.ALL_BACKENDS_DOWN,
                message="All backends are unhealthy. Portal 5 cannot serve requests.",
            )
            self._schedule(self.dispatch(event))
            logger.error("ALL BACKENDS DOWN — alert fired")

        # Clear debounce when at least one backend recovers
        if currently_healthy and self._alerted_all_down:
            self._alerted_all_down = False

    def check_config_error(self, error_message: str) -> None:
        """Fire a CONFIG_ERROR alert."""
        if not self._enabled:
            return
        event = AlertEvent(
            type=EventType.CONFIG_ERROR,
            message=error_message,
        )
        self._schedule(self.dispatch(event))
