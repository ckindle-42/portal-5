---
id: unit-alerts-optional-json-object-for-additional-headers-e-g-auth-tokens
kind: what
title: "ALERTS \u2014 Optional: JSON object for additional headers (e.g. auth tokens)"
sources:
- type: code
  path: portal/platform/inference/notifications/channels/webhook.py
- type: code
  path: portal/platform/inference/notifications/events.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5482838
updated_at: 1784946220.5482838
---

`WEBHOOK_HEADERS` lets a webhook receiver demand authentication. The channel parses the variable as JSON, merges the result into a base header set that already carries `Content-Type: application/json`, and logs a warning and skips the merge when the value is not valid JSON — the request still proceeds without the extra headers. The alert payload posted by `send_alert` includes event, message, backend id, workspace, timestamp, and metadata; the summary payload additionally includes request totals, per-workspace counts, backend health, uptime, and extended metrics.

## Why

Header injection exists because many inbound-webhook targets such as PagerDuty authenticate with a bearer token rather than a shared secret URL. Treating malformed JSON as a soft failure keeps a typo in configuration from silently blocking alert delivery, and the documented payload shape is the contract a custom receiver must parse.
