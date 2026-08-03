---
id: unit-notifications-channel-pushover
kind: mixed
title: "Notification Pushover channel \u2014 push sender"
sources:
- type: code
  path: portal/platform/inference/notifications/channels/pushover.py
  commit: 7b309b21
last_generated_commit: 7b309b21
claims: []
confidence: high
tags:
- authored-v1
- notifications
- platform
created_at: 1785796502.889693
updated_at: 1785796502.889693
---

`PushoverChannel` sends notifications through the Pushover service: it POSTs
the event to Pushover's API with the application token and the target user.

## Why

Pushover is a lightweight push-notification service for phone delivery — one
API call, no chat workspace, no webhook server — which makes it the channel
for an operator who wants alerts on a phone without running a Slack or
Telegram setup. The channel owns the app token and user key configuration.

## Interfaces

`send_alert` and `send_summary` render the event and call `_post`, which
POSTs the data dict to the Pushover endpoint. `_is_configured` requires the
token and user.

## Gotchas

Pushover is outbound-only and expects the app token, not a chat token — the
configuration contract must stay explicit about which credential it consumes,
since the same env-var family name could otherwise be mistaken for a
different service's token.
