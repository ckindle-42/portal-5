"""Portal 5 — Notification channel interface."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from portal_pipeline.notifications.events import AlertEvent, SummaryEvent

logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    """Base class for a notification channel (Slack, Telegram, Email, Pushover, Webhook)."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for logging."""

    @abstractmethod
    async def send_alert(self, event: AlertEvent) -> None:
        """Send an operational alert."""

    @abstractmethod
    async def send_summary(self, event: SummaryEvent) -> None:
        """Send a daily usage summary."""

    async def send(self, event: AlertEvent | SummaryEvent) -> None:
        """Dispatch to the appropriate method, log errors but don't raise."""
        try:
            # Import at runtime for isinstance check
            from portal_pipeline.notifications.events import AlertEvent

            if isinstance(event, AlertEvent):
                await self.send_alert(event)
            else:
                await self.send_summary(event)
            logger.info("%s: notification sent", self.name)
        except Exception as e:
            # Never let a notification failure bubble up — fire and forget
            logger.warning("%s: notification failed: %s", self.name, e)


# Import channel implementations after base class is defined to avoid circular imports
from portal_pipeline.notifications.channels.email import EmailChannel  # noqa: E402
from portal_pipeline.notifications.channels.pushover import PushoverChannel  # noqa: E402
from portal_pipeline.notifications.channels.slack import SlackChannel  # noqa: E402
from portal_pipeline.notifications.channels.telegram import TelegramChannel  # noqa: E402
from portal_pipeline.notifications.channels.webhook import WebhookChannel  # noqa: E402

__all__ = [
    "NotificationChannel",
    "SlackChannel",
    "TelegramChannel",
    "EmailChannel",
    "PushoverChannel",
    "WebhookChannel",
]
