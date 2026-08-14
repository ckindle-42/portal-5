---
id: unit-alerts-slack
kind: what
title: "ALERTS \u2014 Slack"
sources:
- type: code
  path: portal/platform/inference/notifications/channels/slack.py
- type: code
  path: portal/platform/inference/notifications/events.py
- type: code
  path: .env.example
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5462432
updated_at: 1784946220.5462432
---

Slack delivery rides on an Incoming Webhook URL. `SLACK_ALERT_WEBHOOK_URL` is required; `SLACK_ALERT_CHANNEL` defaults to `#portal-alerts` and is included in the message payload so a webhook pinned to one channel can still be overridden. Both alerts and summaries POST a single text block formatted by the event's Slack renderer, which prefixes each event type with an emoji marker.

## Why

Incoming webhooks are the lowest-friction Slack integration and match the credential-light posture of the rest of the alert layer. Emitting a plain text payload keeps the transport independent of message content, so a future change to the renderer never requires receivers to change, and the default channel keeps configuration to a single required variable.
