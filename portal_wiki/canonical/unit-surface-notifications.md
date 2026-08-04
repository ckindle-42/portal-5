---
id: unit-surface-notifications
kind: mixed
title: "Notifications subsystem \u2014 alert fan-out over a channel ABC"
sources:
- type: code
  path: portal/platform/inference/notifications/*.py
- type: code
  path: portal/platform/inference/notifications/channels/*.py
last_generated_commit: 22007054d6cba73357ea3c5d7d7c97f5c252d7dc
claims: []
confidence: high
tags:
- authored-v1
- platform
- notifications
created_at: 1785886200.0
updated_at: 1785886200.0
---

The notifications subsystem is the operational-alert surface: backend-down and
recovery events, configuration errors, and daily usage summaries fan out to
operators through channel transports. The health loop never touches channel
plumbing — it hands events to the dispatcher, which owns the fan-out and the
threshold logic.

## Why

Alerting policy lives in one place instead of being scattered across monitoring
paths. The `NotificationChannel` abstraction is the polymorphism point: the
dispatcher holds abstract instances and calls `send_alert` and `send_summary`
without knowing which transport it is talking to, so adding a channel never
touches the health loop. The typed vocabulary exists because each event kind
needs a distinct rendering and severity rather than a free-form message channels
must parse.

## Interfaces

`NotificationChannel` declares abstract `send_alert` and `send_summary` plus the
`_is_configured` convention that turns an unconfigured transport into a no-op.
`EventType` enumerates the kinds while `AlertEvent` and `SummaryEvent` carry
structured fields. `NotificationDispatcher` registers channels via `add_channel`;
`check_thresholds_and_alert` tracks consecutive failures per backend and fires
transition events. `NotificationScheduler` drives summaries through a
`CronTrigger`, inert when APScheduler is absent.

## Gotchas

Transport hazards are channel-specific: Pushover wants an app token, not a chat
token; Telegram renderings must respect the message length bound; Slack is
configured by incoming webhook, not a bot token; email is best-effort and logs
rather than crashes the loop; the generic webhook passes raw event JSON. A
channel that skips part of the ABC silently drops summaries through the fan-out.
