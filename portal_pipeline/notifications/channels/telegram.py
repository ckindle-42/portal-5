"""Portal 5 — Telegram notification channel via bot API."""

import logging
import os
from typing import TYPE_CHECKING

import httpx

from portal_pipeline.notifications.channels import NotificationChannel

if TYPE_CHECKING:
    from portal_pipeline.notifications.events import AlertEvent, SummaryEvent

logger = logging.getLogger(__name__)


class TelegramChannel(NotificationChannel):
    """Sends notifications to a Telegram channel via bot sendMessage API."""

    name = "Telegram"

    def _is_configured(self) -> bool:
        token = os.environ.get("TELEGRAM_ALERT_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_ALERT_CHANNEL_ID", "")
        return bool(token and chat_id)

    def _bot_url(self, method: str) -> str:
        token = os.environ["TELEGRAM_ALERT_BOT_TOKEN"]
        return f"https://api.telegram.org/bot{token}/{method}"

    async def _send_message(self, text: str) -> None:
        payload = {
            "chat_id": os.environ["TELEGRAM_ALERT_CHANNEL_ID"],
            "text": text,
            "parse_mode": "Markdown",
        }
        if self._client is not None:
            resp = await self._client.post(
                self._bot_url("sendMessage"),
                json=payload,
                timeout=10.0,
            )
            resp.raise_for_status()
        else:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self._bot_url("sendMessage"),
                    json=payload,
                    timeout=10.0,
                )
                resp.raise_for_status()

    async def send_alert(self, event: "AlertEvent") -> None:
        if not self._is_configured():
            return
        await self._send_message(event.format_telegram())

    async def send_summary(self, event: "SummaryEvent") -> None:
        if not self._is_configured():
            return
        await self._send_message(event.format_telegram())
