---
id: unit-alerts-enable-disable-daily-summary-default-true
kind: what
title: "ALERTS \u2014 Enable/disable daily summary (default: true)"
sources:
- type: code
  path: portal/platform/inference/notifications/scheduler.py
- type: code
  path: portal/platform/inference/notifications/dispatcher.py
- type: code
  path: .env.example
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.550015
updated_at: 1784946220.550015
---

`ALERT_SUMMARY_ENABLED` gates the scheduler independently of the alert path. When the variable is false, the scheduler logs that summaries are disabled via env and never registers the cron job; when it is unset entirely, the code defaults to true. The gate stacks on top of the master `NOTIFICATIONS_ENABLED` switch, so both must be truthy for a summary to actually be dispatched.

## Why

The summary is the one notification operators routinely want to silence without disabling urgent alerts, so it earns its own gate. Defaulting to true preserves out-of-the-box behavior for anyone who only flipped the master switch, while the stacked arrangement keeps the scheduler a strict subset of the dispatcher's overall enablement.
