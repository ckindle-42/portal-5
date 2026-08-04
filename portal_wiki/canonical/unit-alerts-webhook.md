---
id: unit-alerts-webhook
kind: what
title: "ALERTS \u2014 Webhook"
sources:
- type: code
  path: portal/platform/inference/notifications/channels/webhook.py
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
created_at: 1784946220.54787
updated_at: 1784946220.54787
---

The webhook channel POSTs a JSON body to any URL given by `WEBHOOK_URL`, which is required and must be a real value rather than the literal string false. Alerts and summaries use the same transport and differ only in the fields they post. `WEBHOOK_HEADERS` supports bearer-token receivers, content type is always application/json with a Portal user agent, and the HTTP timeout is fixed at ten seconds.

## Why

A generic webhook is the escape hatch of the alert layer: PagerDuty, SIEM collectors, and custom bots all speak inbound JSON POST, so one channel covers receivers no dedicated integration would. A short fixed timeout keeps a dead endpoint from hanging the dispatch task, while raising on HTTP errors surfaces delivery failures into the pipeline log.
