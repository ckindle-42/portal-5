---
id: unit-alerts-hour-to-send-summary-0-23-default-8
kind: what
title: "ALERTS \u2014 Hour to send summary (0-23, default: 8)"
sources:
- type: code
  path: portal/platform/inference/notifications/scheduler.py
- type: code
  path: portal/platform/inference/router/lifespan.py
- type: code
  path: .env.example
- type: code
  path: deploy/portal-5/docker-compose.yml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.550354
updated_at: 1784946220.550354
---

`ALERT_SUMMARY_HOUR` selects the hour at which the daily summary fires; the scheduler plugs it into a `CronTrigger` with the minute fixed at zero. The example environment ships 8 and the compose service forwards a default of 8, so the effective send time is eight in the configured timezone. Only if the variable is stripped entirely does the in-process fallback of nine apply, which is why the shipped default and the code default differ.

## Why

Two defaults exist because the shipped environment and the code's resilience are different concerns: compose always injects a value, making the runtime default mostly theoretical, while the code fallback of nine exists only so the scheduler still runs when the variable is absent. Documenting both prevents confusion when a log shows an unexpected send hour.
