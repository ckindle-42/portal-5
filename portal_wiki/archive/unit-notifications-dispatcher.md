---
id: unit-notifications-dispatcher
kind: mixed
title: "Notification dispatcher \u2014 fan-out + threshold alerting"
sources:
- type: code
  path: portal/platform/inference/notifications/dispatcher.py
  commit: 7b309b21
last_generated_commit: 7b309b21
claims: []
confidence: high
tags:
- authored-v1
- notifications
- platform
created_at: 1785796462.796395
updated_at: 1785796462.796395
---

The notification dispatcher fans events out to every configured channel. It
holds the channel list, routes each event to each channel's send method, and
provides the threshold-based health-check entry point that decides when a
backend-down condition becomes an alert.

## Why

Fan-out is the design's core: adding a notification channel should never
require touching the health loop or the benchmark code. The dispatcher is the
single place channels are registered and events are routed, so the health
loop calls one method and every configured channel gets the event. The
threshold logic (when does a backend being down escalate to an alert, when
does recovery clear it) lives here rather than in the health code so the
alerting policy is one place an operator can tune.

## Interfaces

`NotificationDispatcher` provides `add_channel`, `check_thresholds_and_alert`
(which takes the backend registry and compares against thresholds), and the
per-event send methods that route to all registered channels. The event types
come from `events`.

## Gotchas

A channel that is not configured must be a no-op, not a crash — the
dispatcher relies on each channel's `_is_configured` guard so a missing Slack
token does not take down the health loop that called it.
