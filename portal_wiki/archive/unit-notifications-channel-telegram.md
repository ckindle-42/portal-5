---
id: unit-notifications-channel-telegram
kind: mixed
title: "Notification Telegram channel \u2014 Bot API sender"
sources:
- type: code
  path: portal/platform/inference/notifications/channels/telegram.py
  commit: 7b309b21
last_generated_commit: 7b309b21
claims: []
confidence: high
tags:
- authored-v1
- notifications
- platform
created_at: 1785796491.42516
updated_at: 1785796491.42516
---

`TelegramChannel` sends notifications to a Telegram chat via the Bot API: it
formats the event into a text message and POSTs it to the bot's `sendMessage`
endpoint.

## Why

Telegram is the second common operator channel, and its Bot API is a simple
token-authenticated POST — no webhook server needed because the channel is
outbound only. The channel owns the bot token and the target chat id from
configuration, so an operator needs no Slack workspace to get alerts.

## Interfaces

`send_alert` and `send_summary` render the event to text and call
`_send_message`, which POSTs to `_bot_url("sendMessage")`. `_is_configured`
requires the bot token and a target chat.

## Gotchas

Telegram message length is bounded; a summary that exceeds the limit would be
truncated or rejected by the API, so the channel must keep its renderings
within the platform's message size.
