"""Portal 5 — Notification event types."""

import html as _html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class EventType(Enum):
    """Types of notification events."""

    BACKEND_DOWN = "backend_down"
    BACKEND_RECOVERED = "backend_recovered"
    ALL_BACKENDS_DOWN = "all_backends_down"
    CONFIG_ERROR = "config_error"
    DAILY_SUMMARY = "daily_summary"


@dataclass
class AlertEvent:
    """An operational alert — fired immediately when a threshold is crossed."""

    type: EventType
    message: str
    backend_id: str | None = None
    workspace: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)

    def format_slack(self) -> str:
        """Format for Slack notification."""
        emoji = {
            EventType.BACKEND_DOWN: ":warning:",
            EventType.BACKEND_RECOVERED: ":white_check_mark:",
            EventType.ALL_BACKENDS_DOWN: ":rotating_light:",
            EventType.CONFIG_ERROR: ":x:",
        }.get(self.type, ":bell:")

        lines = [f"{emoji} *Portal 5 Alert — {self.type.value}*"]
        lines.append(self.message)
        if self.backend_id:
            lines.append(f"`backend_id`: {self.backend_id}")
        if self.workspace:
            lines.append(f"`workspace`: {self.workspace}")
        lines.append(f"_Sent at {self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}_")
        return "\n".join(lines)

    def format_telegram(self) -> str:
        """Format for Telegram notification."""
        prefix = {
            EventType.BACKEND_DOWN: "[WARNING]",
            EventType.BACKEND_RECOVERED: "[RECOVERED]",
            EventType.ALL_BACKENDS_DOWN: "[CRITICAL]",
            EventType.CONFIG_ERROR: "[ERROR]",
        }.get(self.type, "[ALERT]")

        lines = [f"{prefix} Portal 5 — {self.type.value}", "", self.message]
        if self.backend_id:
            lines.append(f"Backend: {self.backend_id}")
        if self.workspace:
            lines.append(f"Workspace: {self.workspace}")
        lines.append(f"Sent at {self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        return "\n".join(lines)

    def format_email(self, plaintext: bool = False) -> str:
        """Format for email notification."""
        sep = "\n" if plaintext else "<br>"
        lines = [
            f"<b>Portal 5 — {_html.escape(self.type.value.upper())}</b>",
            "",
            _html.escape(self.message),
        ]
        if self.backend_id:
            lines.append(f"{sep}Backend ID: {_html.escape(self.backend_id)}")
        if self.workspace:
            lines.append(f"{sep}Workspace: {_html.escape(self.workspace)}")
        lines.extend(["", f"Sent at {self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}"])
        return "\n".join(lines)

    def format_pushover(self) -> str:
        """Format for Pushover notification (max 512 chars)."""
        prefix = {
            EventType.BACKEND_DOWN: "[DOWN]",
            EventType.BACKEND_RECOVERED: "[OK]",
            EventType.ALL_BACKENDS_DOWN: "[CRITICAL]",
            EventType.CONFIG_ERROR: "[ERROR]",
        }.get(self.type, "[ALERT]")
        msg = f"{prefix} {self.message}"
        if self.backend_id:
            msg += f" | backend={self.backend_id}"
        return msg[:512]


@dataclass
class SummaryEvent:
    """A daily usage summary — built from pipeline metrics."""

    timestamp: datetime
    total_requests: int
    requests_by_workspace: dict[str, int]
    healthy_backends: int
    total_backends: int
    uptime_seconds: float
    # Extended metrics (new)
    requests_by_model: dict[str, int] = field(default_factory=dict)
    avg_tokens_per_second: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    avg_response_time_ms: float = 0.0
    # New metrics
    errors_by_type: dict[str, int] = field(default_factory=dict)
    total_errors: int = 0
    peak_concurrent: int = 0
    persona_usage: dict[str, int] = field(default_factory=dict)
    type: EventType = field(default=EventType.DAILY_SUMMARY)

    def format_slack(self) -> str:
        """Format for Slack."""
        uptime_h = self.uptime_seconds / 3600
        lines = [
            ":chart_with_upwards_trend: *Portal 5 — Daily Usage Summary*",
            f"_Generated at {self.timestamp.strftime('%Y-%m-%d %H:%M UTC')}_",
            "",
            f"*Total Requests:* {self.total_requests:,}",
            f"*Total Errors:* {self.total_errors:,}",
            f"*Uptime:* {uptime_h:.1f} hours",
            f"*Healthy Backends:* {self.healthy_backends}/{self.total_backends}",
            f"*Peak Concurrent:* {self.peak_concurrent}",
            f"*Avg TPS:* {self.avg_tokens_per_second:.1f} tok/s",
            f"*Avg Response Time:* {self.avg_response_time_ms:.0f}ms",
            f"*Tokens:* {self.total_input_tokens:,} in / {self.total_output_tokens:,} out",
            "",
            "*Requests by Workspace:*",
        ]
        for ws, count in sorted(self.requests_by_workspace.items(), key=lambda x: -x[1]):
            lines.append(f"  `{ws:32s}` {count:,}")
        if self.errors_by_type:
            lines.append("")
            lines.append("*Errors by Type:*")
            for err_type, count in sorted(self.errors_by_type.items(), key=lambda x: -x[1]):
                lines.append(f"  `{err_type}` {count:,}")
        if self.requests_by_model:
            lines.append("")
            lines.append("*Top Models:*")
            for model, count in sorted(self.requests_by_model.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"  `{model}` {count:,}")
        if self.persona_usage:
            lines.append("")
            lines.append("*Persona Usage:*")
            for persona, count in sorted(self.persona_usage.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"  `{persona}` {count:,}")
        return "\n".join(lines)

    def format_telegram(self) -> str:
        """Format for Telegram."""
        uptime_h = self.uptime_seconds / 3600
        lines = [
            "📊 *Portal 5 — Daily Summary*",
            "",
            f"Total Requests: {self.total_requests:,}",
            f"Total Errors: {self.total_errors:,}",
            f"Uptime: {uptime_h:.1f}h",
            f"Healthy Backends: {self.healthy_backends}/{self.total_backends}",
            f"Peak Concurrent: {self.peak_concurrent}",
            f"Avg TPS: {self.avg_tokens_per_second:.1f}",
            f"Avg Response: {self.avg_response_time_ms:.0f}ms",
            f"Tokens: {self.total_input_tokens:,} in / {self.total_output_tokens:,} out",
        ]
        if self.errors_by_type:
            lines.append("")
            lines.append("Errors by Type:")
            for err_type, count in sorted(self.errors_by_type.items(), key=lambda x: -x[1]):
                lines.append(f"  {err_type}: {count:,}")
        lines.append("")
        lines.append("Requests by Workspace:")
        for ws, count in sorted(self.requests_by_workspace.items(), key=lambda x: -x[1]):
            lines.append(f"  {ws}: {count:,}")
        if self.requests_by_model:
            lines.append("")
            lines.append("Top Models:")
            for model, count in sorted(self.requests_by_model.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"  {model}: {count:,}")
        if self.persona_usage:
            lines.append("")
            lines.append("Persona Usage:")
            for persona, count in sorted(self.persona_usage.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"  {persona}: {count:,}")
        return "\n".join(lines)

    def format_email(self) -> str:
        """Format for email."""
        uptime_h = self.uptime_seconds / 3600
        lines = [
            "<b>Portal 5 — Daily Usage Summary</b>",
            "",
            f"<b>Total Requests:</b> {self.total_requests:,}",
            f"<b>Uptime:</b> {uptime_h:.1f} hours",
            f"<b>Healthy Backends:</b> {self.healthy_backends}/{self.total_backends}",
            f"<b>Avg Tokens/sec:</b> {self.avg_tokens_per_second:.1f}",
            f"<b>Avg Response Time:</b> {self.avg_response_time_ms:.0f}ms",
            f"<b>Input Tokens:</b> {self.total_input_tokens:,}",
            f"<b>Output Tokens:</b> {self.total_output_tokens:,}",
            "",
            "<b>Requests by Workspace:</b>",
            "<ul>",
        ]
        for ws, count in sorted(self.requests_by_workspace.items(), key=lambda x: -x[1]):
            lines.append(f"<li>{_html.escape(ws)}: {count:,}</li>")
        lines.append("</ul>")
        if self.requests_by_model:
            lines.append("<b>Top Models:</b><ul>")
            for model, count in sorted(self.requests_by_model.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"<li>{_html.escape(model)}: {count:,}</li>")
            lines.append("</ul>")
        lines.append(f"<p>Generated at {self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>")
        return "\n".join(lines)

    def format_pushover(self) -> str:
        """Format for Pushover (max 512 chars)."""
        uptime_h = self.uptime_seconds / 3600
        # Pushover is compact - include key metrics only
        msg = (
            f"📊 Portal 5: {self.total_requests:,} req, {uptime_h:.0f}h uptime, "
            f"{self.avg_tokens_per_second:.0f} tok/s, {self.avg_response_time_ms:.0f}ms avg, "
            f"{self.healthy_backends}/{self.total_backends} backends"
        )
        return msg[:512]
