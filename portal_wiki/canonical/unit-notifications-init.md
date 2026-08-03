---
id: unit-notifications-init
kind: mixed
title: "Notifications subsystem \u2014 operational alert surface"
sources:
- type: code
  path: portal/platform/inference/notifications/__init__.py
  commit: 7b309b21
last_generated_commit: 7b309b21
claims: []
confidence: high
tags:
- authored-v1
- notifications
- platform
created_at: 1785796451.3297448
updated_at: 1785796451.3297448
---

The notifications subsystem is Portal's operational-alert surface: it sends
backend-down alerts and daily usage summaries over Slack, Telegram, email, and
Pushover, and exposes the dispatcher and scheduler as the public entry points.

## Why

The package exists so the health loop has one way to reach an operator instead
of each monitoring path embedding its own channel logic. The dispatcher is the
fan-out point and the scheduler is the daily-summary driver; keeping them in a
dedicated subsystem means a health check calls `dispatcher.check_thresholds_and_alert`
and the channel plumbing stays out of the health-check code.

## Interfaces

`NotificationDispatcher` (from `dispatcher`) and `NotificationScheduler` (from
`scheduler`) are the public surface. A caller constructs the dispatcher, adds
the channels it wants (e.g. `SlackChannel()`, `TelegramChannel()`), starts the
scheduler for daily summaries, and calls the threshold check from the health
loop.
