---
id: unit-notifications-channel-webhook
kind: mixed
title: "Notification webhook channel \u2014 generic JSON POST"
sources:
- type: code
  path: portal/platform/inference/notifications/channels/webhook.py
  commit: 7b309b21
last_generated_commit: 7b309b21
claims: []
confidence: high
tags:
- authored-v1
- notifications
- platform
created_at: 1785796479.9727209
updated_at: 1785796479.9727209
---

`WebhookChannel` is the generic webhook notification channel: it POSTs the
alert or summary payload as JSON to a configured endpoint URL.

## Why

A generic webhook exists because not every operator wants Slack, Telegram,
email, or Pushover — many have an existing webhook aggregator or a custom
dashboard that accepts JSON. It is the escape hatch that covers a deployment
whose channel is not one of the four named ones, and because it is just a
JSON POST it is the easiest channel to test and to integrate with a local
service.

## Interfaces

`WebhookChannel.send_alert` and `send_summary` serialise the event to JSON
and POST it to the configured URL with an `httpx.AsyncClient`. The URL comes
from environment configuration, and the channel is a no-op when unset.

## Gotchas

As the least-structured channel, the webhook passes the raw event JSON — it
does no rendering, so downstream consumers must handle the event schema
themselves.
