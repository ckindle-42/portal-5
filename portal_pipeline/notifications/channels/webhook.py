"""Portal 5 — Generic webhook notification channel."""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

import httpx

from portal_pipeline.notifications.channels import NotificationChannel

if TYPE_CHECKING:
    from portal_pipeline.notifications.events import AlertEvent, SummaryEvent

logger = logging.getLogger(__name__)


class WebhookChannel(NotificationChannel):
    """Sends notifications to an arbitrary HTTP endpoint as JSON POST.

    Configure via environment variables:
      WEBHOOK_URL     Full URL to POST to (required)
      WEBHOOK_HEADERS JSON string of additional headers, e.g. '{"Authorization": "Bearer ..."}' (optional)
    """

    name = "Webhook"

    def _is_configured(self) -> bool:
        url = os.environ.get("WEBHOOK_URL", "")
        return bool(url and url != "false")

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "User-Agent": "Portal5-Notifications/1.0"}
        raw = os.environ.get("WEBHOOK_HEADERS", "").strip()
        if raw:
            try:
                extra = json.loads(raw)
                if isinstance(extra, dict):
                    headers.update(extra)
            except json.JSONDecodeError:
                logger.warning("WebhookChannel: WEBHOOK_HEADERS is not valid JSON — ignoring")
        return headers

    async def _post(self, body: dict) -> None:
        headers = self._get_headers()
        timeout = 10.0
        if self._client is not None:
            resp = await self._client.post(
                os.environ["WEBHOOK_URL"],
                json=body,
                headers=headers,
                timeout=timeout,
            )
            resp.raise_for_status()
        else:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    os.environ["WEBHOOK_URL"],
                    json=body,
                    headers=headers,
                    timeout=timeout,
                )
                resp.raise_for_status()

    async def send_alert(self, event: AlertEvent) -> None:
        if not self._is_configured():
            return
        await self._post(
            {
                "event": event.type.value,
                "message": event.message,
                "backend_id": event.backend_id,
                "workspace": event.workspace,
                "timestamp": event.timestamp.isoformat(),
                "metadata": event.metadata,
            }
        )

    async def send_summary(self, event: SummaryEvent) -> None:
        if not self._is_configured():
            return
        await self._post(
            {
                "event": event.type.value,
                "timestamp": event.timestamp.isoformat(),
                "total_requests": event.total_requests,
                "requests_by_workspace": event.requests_by_workspace,
                "healthy_backends": event.healthy_backends,
                "total_backends": event.total_backends,
                "uptime_seconds": event.uptime_seconds,
                # Extended metrics
                "requests_by_model": event.requests_by_model,
                "avg_tokens_per_second": event.avg_tokens_per_second,
                "total_input_tokens": event.total_input_tokens,
                "total_output_tokens": event.total_output_tokens,
                "avg_response_time_ms": event.avg_response_time_ms,
            }
        )
