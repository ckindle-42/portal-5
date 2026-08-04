---
id: unit-notifications-channel-email
kind: mixed
title: "Notification email channel \u2014 SMTP sender"
sources:
- type: code
  path: portal/platform/inference/notifications/channels/email.py
  commit: 7b309b21
last_generated_commit: 7b309b21
claims: []
confidence: high
tags:
- authored-v1
- notifications
- platform
created_at: 1785796497.1787462
updated_at: 1785796497.1787462
---

`EmailChannel` sends notifications by SMTP: it builds a subject and an HTML
body from the event and sends them through the configured mail server.

## Why

Email is the fallback channel that works for every operator even when Slack
and Telegram are unavailable, and HTML body rendering lets an alert carry
structure (tables, severity colouring) that plain text cannot. The channel
owns the SMTP configuration — host, credentials, from/to addresses — so the
dispatcher stays channel-agnostic.

## Interfaces

`send_alert` and `send_summary` build the subject/HTML pair and call
`_send_email`, which performs the SMTP send. `_is_configured` gates on the
SMTP host and recipient being present.

## Gotchas

SMTP failures must not crash the health loop — the channel is best-effort,
and an unreachable mail server should be logged and skipped rather than
raised through the dispatcher's fan-out.
