---
id: unit-alerts-webhook
kind: what
title: "ALERTS \u2014 Webhook"
sources:
- type: doc
  path: docs/ALERTS.md
  commit: 05e42ec2
  section: Webhook
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.54787
updated_at: 1784946220.54787
---

POST JSON to any HTTP endpoint — works with PagerDuty, custom receivers, SIEM systems, or any service that accepts inbound webhooks.

```bash
echo "WEBHOOK_URL=https://your-endpoint.example.com/portal-events" >> .env
