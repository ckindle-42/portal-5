---
id: unit-notifications-channel-slack
kind: mixed
title: "Notification Slack channel \u2014 incoming-webhook sender"
sources:
- type: code
  path: portal/platform/inference/notifications/channels/slack.py
  commit: 7b309b21
last_generated_commit: 7b309b21
claims: []
confidence: high
tags:
- authored-v1
- notifications
- platform
created_at: 1785796485.719061
updated_at: 1785796485.719061
---

`SlackChannel` sends notifications to a Slack webhook: it formats the alert
or summary into a Slack message payload and POSTs it to the configured
incoming-webhook URL.

## Why

Slack is the most common operator channel, and the incoming-webhook approach
keeps the channel simple: no bot token, no Socket Mode, just an HTTP POST of
a message payload. The formatting is specific to Slack's message shape (text
blocks, markdown-ish links), so the rendering lives here where the Slack
idiom belongs rather than in the shared dispatcher.

## Interfaces

`SlackChannel.send_alert` and `send_summary` build the Slack payload from the
event and POST it. `_is_configured` gates on the webhook URL being present.

## Gotchas

The channel is configured by webhook URL, not by a bot token — pointing it at
a Slack app that expects the Socket Mode protocol would silently fail, which
is why the configuration contract is explicit about the incoming webhook.
