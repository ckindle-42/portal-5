---
id: unit-p5-roadmap-p5-fut-004-webhook-based-event-notifications
kind: what
title: "P5_ROADMAP \u2014 P5-FUT-004: Webhook-Based Event Notifications"
sources:
- type: code
  path: portal/platform/inference/notifications/channels/webhook.py
- type: code
  path: .env.example
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.590606
updated_at: 1784946220.590606
---

P5-FUT-004 is implemented. `WebhookChannel`
(`portal/platform/inference/notifications/channels/webhook.py`) is a
`NotificationChannel` registered in
`portal/platform/inference/notifications/channels/__init__.py` and POSTs a JSON
body to `WEBHOOK_URL` for both alert and daily-summary events. `send_alert`
carries the event type, message, backend id, workspace and timestamp;
`send_summary` carries request totals, per-workspace counts, backend health,
uptime, token metrics and average latency. `WEBHOOK_HEADERS`, a JSON object,
adds extra request headers and is ignored with a warning when unparsable. The
channel only activates when `WEBHOOK_URL` is set to a value other than "false".
Both env vars are documented in `.env.example`. The dispatcher
(`portal/platform/inference/notifications/dispatcher.py`) fans each event out to
every registered channel asynchronously, so webhook delivery is fire-and-forget
alongside the Slack, Pushover, Telegram, and Email channels.

## Why

`WebhookChannel` exists because alert delivery needs a generic operator-defined
sink that needs no external account: a JSON POST to an arbitrary HTTP endpoint
is the lowest-friction route for custom notification consumers. Keeping the two
event shapes (`send_alert` / `send_summary`) separate lets a receiver distinguish
a per-backend failure from the periodic digest without parsing the payload, and
the header override covers authenticated endpoints without storing credentials
in the repo.
