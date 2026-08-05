---
id: unit-HOWTO-18-notifications-alerts
kind: why
title: "HOWTO \u2014 18. Notifications & Alerts"
sources:
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: .env.example
last_generated_commit: ca0f99d64c0644df1d5fc30674b6c476fceb1a42
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.856343
updated_at: 1783195000.856343
---

**What:** Get operational alerts and daily usage summaries via Slack, Telegram, Email, Pushover, or a generic webhook.

**How:** The pipeline's notification dispatcher (`portal/platform/inference/notifications/`) fires `AlertEvent` and `SummaryEvent` messages to every configured channel. Enable it with `NOTIFICATIONS_ENABLED=true` in `.env` (default `false`). Each channel is configured by its env var in `.env.example`:

- Slack: `SLACK_ALERT_WEBHOOK_URL` / `SLACK_ALERT_CHANNEL`
- Telegram: `TELEGRAM_ALERT_BOT_TOKEN` / `TELEGRAM_ALERT_CHANNEL_ID`
- Email: `SMTP_HOST` plus the `EMAIL_ALERT_TO` recipient
- Pushover: `PUSHOVER_API_TOKEN` + `PUSHOVER_USER_KEY`
- Generic: `WEBHOOK_URL`

The daily summary is scheduled by `ALERT_SUMMARY_ENABLED` (default true), `ALERT_SUMMARY_HOUR`, and `ALERT_SUMMARY_TIMEZONE`.

**Verify:** `POST /notifications/test` on the pipeline (`portal/platform/inference/router/handlers.py`) fires a real test alert plus a summary with live request counts, and reports the per-channel configured state. It answers 503 when the dispatcher is disabled.

## Why

Alerting lives in the pipeline process rather than a separate daemon so it shares the request telemetry it reports on — the daily summary needs live counters, so it reads them from the same memory the router writes. Channel configuration is pure env plumbing, which keeps notification support out of Open WebUI and lets an operator add a channel without a rebuild.
