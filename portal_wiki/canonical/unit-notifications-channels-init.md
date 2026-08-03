---
id: unit-notifications-channels-init
kind: mixed
title: "Notification channels \u2014 channel ABC + implementations"
sources:
- type: code
  path: portal/platform/inference/notifications/channels/__init__.py
  commit: 7b309b21
last_generated_commit: 7b309b21
claims: []
confidence: high
tags:
- authored-v1
- notifications
- platform
created_at: 1785796474.2595782
updated_at: 1785796474.2595782
---

The channels subpackage defines the `NotificationChannel` abstract base class
and hosts the concrete channel implementations — Slack, Telegram, email,
Pushover, and a generic webhook. The ABC pins the contract every channel
must implement.

## Why

The abstract base is the polymorphism point that makes the dispatcher's fan-out
work: the dispatcher holds `NotificationChannel` instances and calls their send
methods without knowing which concrete channel it is talking to. The
`send_alert`/`send_summary` split mirrors the two event kinds, and the
`_is_configured` convention is how the dispatcher's no-op guarantee is
implemented — a channel that has no credentials configured simply does not
send.

## Interfaces

`NotificationChannel` declares the abstract `send_alert` and `send_summary`
methods; concrete subclasses in the sibling modules implement them. The
constructor accepts an optional `httpx.AsyncClient` for test injection.

## Gotchas

New channels must implement the full ABC — a half-channel that only sends
alerts would silently drop summaries through the dispatcher's fan-out.
