---
id: unit-alerts-troubleshooting
kind: what
title: "ALERTS \u2014 Troubleshooting"
sources:
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: portal/platform/inference/notifications/channels/webhook.py
- type: code
  path: portal/platform/inference/notifications/channels/email.py
- type: code
  path: portal/platform/inference/notifications/scheduler.py
- type: code
  path: portal/platform/inference/router/state.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.551797
updated_at: 1784946220.551797
---

Debugging follows the enablement chain. If nothing arrives, confirm `NOTIFICATIONS_ENABLED` is true, that the pipeline was restarted after the environment changed, then POST `/notifications/test` for per-channel config status. For webhooks verify `WEBHOOK_URL` accepts a JSON POST and that `WEBHOOK_HEADERS`, when set, parses; malformed JSON is logged and ignored. Email requires the port to match the provider, 587 for STARTTLS and 465 for SSL. The daily summary no longer resets on restart: metrics persist to `/app/data/metrics_state.json` every sixty seconds and the delta snapshot lives beside it, with guards that skip an empty first-day report.

## Why

Every failure mode here traces back to a small set of causes: environment not read, endpoint unreachable, or a restart gap. Because the summary reads persisted state rather than pure memory, the older advice that a restart between midnight and summary time zeroes the numbers is no longer accurate, and correcting it prevents operators from chasing a phantom reset.
