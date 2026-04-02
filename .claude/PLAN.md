# Plan: Portal 5 Event Notifications System (P5-FUT-004)

## What We're Building

A notification system that pushes operational alerts and daily usage summaries via:
- **Slack** (webhook or chat_postMessage to a configured channel)
- **Telegram** (bot message to a configured channel chat ID)
- **Email** (SMTP to a configured address)
- **Pushover** (HTTP API to Pushover endpoint)

**Two notification types:**
1. **Operational alerts** — fired immediately when threshold events occur
2. **Daily usage summaries** — fired once per day at a configured hour (default: 09:00)

**Approach: dedicated notifications module inside `portal_pipeline/`, not a separate MCP service.**

---

## Architecture

```
portal_pipeline/
├── notifications/
│   ├── __init__.py
│   ├── dispatcher.py       # Unified event bus — fans out to all configured channels
│   ├── channels/
│   │   ├── __init__.py
│   │   ├── slack.py        # Slack webhook sender
│   │   ├── telegram.py     # Telegram bot sender (bot, not user-facing bot)
│   │   ├── email.py        # SMTP sender
│   │   └── pushover.py     # Pushover API sender
│   ├── events.py           # Event type definitions (AlertEvent, SummaryEvent)
│   ├── scheduler.py        # APScheduler — daily summary trigger
│   └── thresholds.py       # Configurable thresholds that fire alerts
```

**Event flow:**
```
Health check loop → threshold check → AlertEvent
                                   → dispatcher.dispatch(event)
                                       → slack.send(...)
                                       → telegram.send(...)
                                       → email.send(...)
                                       → pushover.send(...)

APScheduler (daily 09:00) → build SummaryEvent from _request_count
                           → dispatcher.dispatch(event)
```

**Key design decisions:**
- Channels are independently configured (any subset enabled)
- Async send with timeout — notification failure never blocks the pipeline
- Summary uses in-memory `_request_count` (per-worker, reset on restart — acceptable for summaries)
- Alerts fire on state changes (not every health check failure — avoids spam)

---

## Config: New env vars in `.env.example`

```
# ── Notifications ────────────────────────────────────────────────────────────
NOTIFICATIONS_ENABLED=false

# Slack
SLACK_ALERT_WEBHOOK_URL=          # Incoming webhook URL for #portal-alerts
SLACK_ALERT_CHANNEL=#portal-alerts

# Telegram (dedicated alert bot, separate from user-facing bot)
TELEGRAM_ALERT_BOT_TOKEN=         # Bot token for the alert bot
TELEGRAM_ALERT_CHANNEL_ID=         # Channel ID or username (e.g. -1001234567890)

# Email
SMTP_HOST=localhost
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=portal@portal.local
EMAIL_ALERT_TO=admin@portal.local

# Pushover
PUSHOVER_API_TOKEN=
PUSHOVER_USER_KEY=

# Alert thresholds
ALERT_BACKEND_DOWN_THRESHOLD=3    # Fire alert after N consecutive failures per backend
ALERT_NO_HEALTHY_BACKENDS=true    # Fire immediately when all backends unhealthy
ALERT_SUMMARY_ENABLED=true
ALERT_SUMMARY_HOUR=9              # Hour (0-23) to send daily summary
ALERT_SUMMARY_TIMEZONE=UTC        # Or America/New_York, etc.
```

---

## New files to create

### 1. `portal_pipeline/notifications/__init__.py`
Exports `NotificationDispatcher`, `AlertEvent`, `SummaryEvent`.

### 2. `portal_pipeline/notifications/events.py`
```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class EventType(Enum):
    BACKEND_DOWN = "backend_down"
    BACKEND_RECOVERED = "backend_recovered"
    ALL_BACKENDS_DOWN = "all_backends_down"
    CONFIG_ERROR = "config_error"
    DAILY_SUMMARY = "daily_summary"

@dataclass
class AlertEvent:
    type: EventType
    message: str
    backend_id: str | None = None
    workspace: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)

@dataclass
class SummaryEvent:
    type: EventType  # always DAILY_SUMMARY
    timestamp: datetime
    total_requests: int
    requests_by_workspace: dict[str, int]
    healthy_backends: int
    total_backends: int
    uptime_seconds: float
```

### 3. `portal_pipeline/notifications/dispatcher.py`
```python
class NotificationDispatcher:
    def __init__(self):
        self._channels: list[NotificationChannel] = []
        self._consecutive_failures: dict[str, int] = defaultdict(int)
        self._alerted_all_down: bool = False  # Debounce: only alert once per "all down" event

    def add_channel(self, channel: NotificationChannel): ...

    async def dispatch(self, event: AlertEvent | SummaryEvent): ...

    async def _send_all(self, event, formatted: str):  # Fire-and-forget, log errors

    def check_thresholds_and_alert(self, registry: BackendRegistry): ...
        # Called by health check loop
        # Increment failure count per backend
        # If threshold crossed → AlertEvent(BACKEND_DOWN)
        # If all down and not yet alerted → AlertEvent(ALL_BACKENDS_DOWN)
        # If any recovered and was alerting all-down → AlertEvent(BACKEND_RECOVERED)
```

### 4. `portal_pipeline/notifications/channels/slack.py`
```python
class SlackChannel(NotificationChannel):
    async def send(self, event, formatted: str) -> None:
        async with httpx.AsyncClient() as client:
            await client.post(
                os.environ["SLACK_ALERT_WEBHOOK_URL"],
                json={"text": formatted, "channel": os.environ.get("SLACK_ALERT_CHANNEL", "#alerts")},
                timeout=10.0,
            )
```

### 5. `portal_pipeline/notifications/channels/telegram.py`
```python
class TelegramChannel(NotificationChannel):
    async def send(self, event, formatted: str) -> None:
        token = os.environ["TELEGRAM_ALERT_BOT_TOKEN"]
        chat_id = os.environ["TELEGRAM_ALERT_CHANNEL_ID"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient() as client:
            await client.post(url, json={"chat_id": chat_id, "text": formatted}, timeout=10.0)
```

### 6. `portal_pipeline/notifications/channels/email.py`
```python
class EmailChannel(NotificationChannel):
    async def send(self, event, formatted: str) -> None:
        msg = MIMEText(formatted)
        msg["Subject"] = f"[Portal 5] {event.type.value}"
        msg["From"] = os.environ["SMTP_FROM"]
        msg["To"] = os.environ["EMAIL_ALERT_TO"]
        async with aiosmtplib.SMTP(...) as smtp:
            await smtp.send_message(msg)
```

### 7. `portal_pipeline/notifications/channels/pushover.py`
```python
class PushoverChannel(NotificationChannel):
    async def send(self, event, formatted: str) -> None:
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://api.pushover.net/1/messages.json",
                data={
                    "token": os.environ["PUSHOVER_API_TOKEN"],
                    "user": os.environ["PUSHOVER_USER_KEY"],
                    "message": formatted,
                    "title": f"Portal 5 — {event.type.value}",
                },
                timeout=10.0,
            )
```

### 8. `portal_pipeline/notifications/scheduler.py`
```python
class NotificationScheduler:
    def __init__(self, dispatcher: NotificationDispatcher):
        self._dispatcher = dispatcher
        self._scheduler = APScheduler()

    def start(self): ...
        self._scheduler.add_job(
            self._send_daily_summary,
            "cron",
            hour=int(os.environ.get("ALERT_SUMMARY_HOUR", "9")),
            timezone=os.environ.get("ALERT_SUMMARY_TIMEZONE", "UTC"),
            id="daily_summary",
        )
        self._scheduler.start()

    async def _send_daily_summary(self):
        # Pull from router_pipe module-level _request_count, _startup_time
        # Build SummaryEvent and dispatch
```

### 9. `portal_pipeline/notifications/thresholds.py`
Tracks consecutive failures per backend and debounce state for "all backends down" alerts.

---

## Integration points in existing files

### `portal_pipeline/router_pipe.py`
```python
# In lifespan startup:
notification_scheduler = NotificationScheduler(dispatcher)
notification_scheduler.start()

# In health check loop (add after health_check_all()):
dispatcher.check_thresholds_and_alert(registry)
```

### `portal_pipeline/cluster_backends.py`
No changes needed — events are derived from the health loop output.

---

## Dependency additions

`pyproject.toml`:
```toml
[project.optional-dependencies]
notifications = [
    "aiosmtplib>=3.0.0",
    "APScheduler>=3.10.0",
]
```

The `httpx` and `python-telegram-bot` deps already exist for other reasons.

---

## Order of implementation

1. **`events.py`** + **`channels/` base** — define types and channel interface
2. **`slack.py`** and **`telegram.py`** — most immediately testable
3. **`dispatcher.py`** — wire events to channels, threshold tracking
4. **`scheduler.py`** — APScheduler daily summary
5. **`email.py`** and **`pushover.py`** — rest of channels
6. **Integrate into `router_pipe.py`** — wire into lifespan + health loop
7. **Add env vars to `.env.example`**
8. **Add `docker-compose.yml` env passthrough** for the notification env vars
9. **Add tests** in `tests/unit/test_notifications.py`
10. **Document** in `docs/ALERTS.md` (new file)

---

## Rollback

If it breaks:
1. `NOTIFICATIONS_ENABLED=false` disables everything — no code changes needed
2. APScheduler shutdown is clean on `docker compose down`
3. All notification sends are fire-and-forget — failures don't affect request handling
4. No database or volume changes
