"""Portal 5 — Email notification channel via SMTP."""

from __future__ import annotations

import logging
import os
import re
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

try:
    import aiosmtplib

    AISMTPLIB_AVAILABLE = True
except ImportError:
    AISMTPLIB_AVAILABLE = False
    aiosmtplib = None  # type: ignore[assignment]

from portal_pipeline.notifications.channels import NotificationChannel

if TYPE_CHECKING:
    from portal_pipeline.notifications.events import AlertEvent, SummaryEvent

logger = logging.getLogger(__name__)


class EmailChannel(NotificationChannel):
    """Sends notifications via SMTP (TLS/STARTTLS)."""

    name = "Email"

    def _is_configured(self) -> bool:
        if not AISMTPLIB_AVAILABLE:
            return False
        host = os.environ.get("SMTP_HOST", "")
        to_addr = os.environ.get("EMAIL_ALERT_TO", "")
        return bool(host and to_addr)

    async def _send_email(self, subject: str, html_body: str) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = os.environ.get("SMTP_FROM", "portal@portal.local")
        msg["To"] = os.environ["EMAIL_ALERT_TO"]

        plain_part = MIMEText(re.sub(r"<[^>]+>", "", html_body).replace("&nbsp;", " "), "plain")
        html_part = MIMEText(html_body, "html")

        msg.attach(plain_part)
        msg.attach(html_part)

        host = os.environ["SMTP_HOST"]
        port = int(os.environ.get("SMTP_PORT", "587"))
        user = os.environ.get("SMTP_USER", "")
        password = os.environ.get("SMTP_PASSWORD", "")

        kwargs: dict = {"hostname": host, "port": port}
        if port == 465:
            kwargs["security_context"] = ssl.create_default_context()
            kwargs["username"] = user
            kwargs["password"] = password
        else:
            kwargs["start_tls"] = True
            if user:
                kwargs["username"] = user
                kwargs["password"] = password

        async with aiosmtplib.SMTP(**kwargs) as smtp:
            await smtp.send_message(msg)

    async def send_alert(self, event: AlertEvent) -> None:
        if not self._is_configured():
            return
        await self._send_email(
            subject=f"[Portal 5] {event.type.value.upper()}",
            html_body=event.format_email(),
        )

    async def send_summary(self, event: SummaryEvent) -> None:
        if not self._is_configured():
            return
        await self._send_email(
            subject="[Portal 5] Daily Usage Summary",
            html_body=event.format_email(),
        )
