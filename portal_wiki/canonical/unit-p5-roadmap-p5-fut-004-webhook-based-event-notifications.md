---
id: unit-p5-roadmap-p5-fut-004-webhook-based-event-notifications
kind: what
title: "P5_ROADMAP \u2014 P5-FUT-004: Webhook-Based Event Notifications"
sources:
- type: doc
  path: P5_ROADMAP.md
  commit: 05e42ec2
  section: 'P5-FUT-004: Webhook-Based Event Notifications'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.590606
updated_at: 1784946220.590606
---

IMPLEMENTED: `WebhookChannel` (`portal/platform/inference/notifications/channels/webhook.py`) sends
JSON POST to any user-defined HTTP endpoint on all alert and daily summary events.
Configure via `WEBHOOK_URL` and optional `WEBHOOK_HEADERS` (JSON object) env vars.
Live-verified: a `config_error` test event was confirmed delivered to a listening endpoint.
