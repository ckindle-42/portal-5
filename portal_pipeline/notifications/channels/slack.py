"""Portal 5 — Slack notification channel via incoming webhook."""

import logging
import os
from typing import TYPE_CHECKING

import httpx

from portal_pipeline.notifications.channels import NotificationChannel

if TYPE_CHECKING:
    from portal_pipeline.notifications.events import AlertEvent, SummaryEvent

logger = logging.getLogger(__name__)


class SlackChannel(NotificationChannel):
    """Sends notifications to a Slack channel via incoming webhook URL."""

    name = "Slack"

    def _is_configured(self) -> bool:
        webhook = os.environ.get("SLACK_ALERT_WEBHOOK_URL", "")
        return bool(webhook and webhook != "false")

    async def _post(self, payload: dict) -> None:
        if self._client is not None:
            resp = await self._client.post(
                os.environ["SLACK_ALERT_WEBHOOK_URL"],
                json=payload,
                timeout=10.0,
            )
            resp.raise_for_status()
        else:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    os.environ["SLACK_ALERT_WEBHOOK_URL"],
                    json=payload,
                    timeout=10.0,
                )
                resp.raise_for_status()

    async def send_alert(self, event: "AlertEvent") -> None:
        if not self._is_configured():
            return
        await self._post(
            {
                "text": event.format_slack(),
                "channel": os.environ.get("SLACK_ALERT_CHANNEL", "#portal-alerts"),
            }
        )

    async def send_summary(self, event: "SummaryEvent") -> None:
        if not self._is_configured():
            return
        await self._post(
            {
                "text": event.format_slack(),
                "channel": os.environ.get("SLACK_ALERT_CHANNEL", "#portal-alerts"),
            }
        )
