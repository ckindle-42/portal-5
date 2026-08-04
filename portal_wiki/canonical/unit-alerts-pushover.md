---
id: unit-alerts-pushover
kind: what
title: "ALERTS \u2014 Pushover"
sources:
- type: code
  path: portal/platform/inference/notifications/channels/pushover.py
- type: code
  path: portal/platform/inference/notifications/events.py
- type: code
  path: .env.example
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.547549
updated_at: 1784946220.547549
---

Pushover requires both `PUSHOVER_API_TOKEN` and `PUSHOVER_USER_KEY`; either missing and the channel stays silent. Alerts post to the Pushover messages endpoint with a title prefixed by the event type, and priority escalates to high only for `backend_down`, `all_backends_down`, and `config_error`; recoveries and summaries send at normal priority. Message bodies are truncated to 512 characters to satisfy the service limit.

## Why

The high-priority mapping encodes that only genuine outages deserve Pushover's urgent sound while routine recoveries and the daily report stay quiet. Truncation exists because the service rejects longer bodies, and the channel deliberately reuses the shared HTTP client rather than opening its own connection pool.
