"""Portal 5 — Notifications subsystem.

Provides operational alerts and daily usage summaries via Slack, Telegram,
Email, and Pushover.

Usage:
    from portal.platform.inference.notifications import NotificationDispatcher, NotificationScheduler

    dispatcher = NotificationDispatcher()
    dispatcher.add_channel(SlackChannel())
    dispatcher.add_channel(TelegramChannel())

    scheduler = NotificationScheduler(dispatcher)
    scheduler.start()

    # In health loop:
    dispatcher.check_thresholds_and_alert(registry)
"""

from portal.platform.inference.notifications.dispatcher import NotificationDispatcher
from portal.platform.inference.notifications.events import AlertEvent, EventType, SummaryEvent
from portal.platform.inference.notifications.scheduler import NotificationScheduler

__all__ = [
    "AlertEvent",
    "EventType",
    "NotificationDispatcher",
    "NotificationScheduler",
    "SummaryEvent",
]
