"""Portal 5 — Pushover notification channel."""

import logging
import os
from typing import TYPE_CHECKING

import httpx

from portal_pipeline.notifications.channels import NotificationChannel

if TYPE_CHECKING:
    from portal_pipeline.notifications.events import AlertEvent, SummaryEvent

logger = logging.getLogger(__name__)


class PushoverChannel(NotificationChannel):
    """Sends notifications via Pushover HTTP API."""

    name = "Pushover"

    def _is_configured(self) -> bool:
        token = os.environ.get("PUSHOVER_API_TOKEN", "")
        user = os.environ.get("PUSHOVER_USER_KEY", "")
        return bool(token and user)

    async def _post(self, data: dict) -> None:
        if self._client is not None:
            resp = await self._client.post(
                "https://api.pushover.net/1/messages.json",
                data=data,
                timeout=10.0,
            )
            resp.raise_for_status()
        else:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.pushover.net/1/messages.json",
                    data=data,
                    timeout=10.0,
                )
                resp.raise_for_status()

    async def send_alert(self, event: "AlertEvent") -> None:
        if not self._is_configured():
            return
        # Priority 1 (high) only for operational alerts that need immediate attention.
        # Priority 0 (normal) for test events, recoveries, and summaries.
        from portal_pipeline.notifications.events import EventType

        high_priority_types = {
            EventType.BACKEND_DOWN,
            EventType.ALL_BACKENDS_DOWN,
            EventType.CONFIG_ERROR,
        }
        priority = "1" if event.type in high_priority_types else "0"
        await self._post(
            {
                "token": os.environ["PUSHOVER_API_TOKEN"],
                "user": os.environ["PUSHOVER_USER_KEY"],
                "message": event.format_pushover(),
                "title": f"Portal 5 — {event.type.value}",
                "priority": priority,
            }
        )

    async def send_summary(self, event: "SummaryEvent") -> None:
        if not self._is_configured():
            return
        await self._post(
            {
                "token": os.environ["PUSHOVER_API_TOKEN"],
                "user": os.environ["PUSHOVER_USER_KEY"],
                "message": event.format_pushover(),
                "title": "Portal 5 — Daily Summary",
                "priority": "0",
            }
        )
