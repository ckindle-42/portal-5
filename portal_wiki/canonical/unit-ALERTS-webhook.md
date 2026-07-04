---
id: unit-ALERTS-webhook
kind: why
title: "ALERTS \u2014 Webhook"
sources:
- type: design
  path: docs/ALERTS.md
  section: Webhook
last_generated_commit: ''
confidence: high
tags:
- docs
- ALERTS
created_at: 1783195000.82042
updated_at: 1783195000.82042
---


POST JSON to any HTTP endpoint — works with PagerDuty, custom receivers, SIEM systems, or any service that accepts inbound webhooks.

```bash
echo "WEBHOOK_URL=https://your-endpoint.example.com/portal-events" >> .env
