---
id: unit-notifications-scheduler
kind: mixed
title: "Notification scheduler \u2014 daily summary cron driver"
sources:
- type: code
  path: portal/platform/inference/notifications/scheduler.py
  commit: 7b309b21
last_generated_commit: 7b309b21
claims: []
confidence: high
tags:
- authored-v1
- notifications
- platform
created_at: 1785796468.494455
updated_at: 1785796468.494455
---

The notification scheduler drives daily usage summaries on a cron schedule
using APScheduler when it is available, and degrades gracefully when it is
not. It collects the day's usage from the metrics store and sends a summary
event through the dispatcher.

## Why

Daily summaries are a time-based concern and should not live inside the
request path. The scheduler isolates that concern and owns the schedule, the
data collection, and the hand-off to the dispatcher. The `APSCHEDULER_AVAILABLE`
guard exists because the pipeline container is deliberately lean — if
APScheduler is not installed, the scheduler must not crash the process; it
simply cannot provide cron behaviour and says so.

## Interfaces

`NotificationScheduler` wraps an `AsyncIOScheduler` with a `CronTrigger` for
the daily summary time, collects usage data, and emits `SummaryEvent` through
the dispatcher. `start`/`stop` manage the scheduler lifecycle.

## Gotchas

The cron trigger time comes from configuration; if APScheduler is absent the
scheduler is inert rather than broken, so a health check that starts it must
not assume a summary will actually be sent.
