---
id: unit-ALERTS-slack
kind: why
title: "ALERTS \u2014 Slack"
sources:
- type: design
  path: docs/ALERTS.md
  section: Slack
last_generated_commit: ''
confidence: high
tags:
- docs
- ALERTS
created_at: 1783195000.819577
updated_at: 1783195000.819577
---


1. Create an Incoming Webhook at [https://api.slack.com/messaging/webhooks](https://api.slack.com/messaging/webhooks)
2. Copy the webhook URL (e.g. `https://hooks.slack.com/services/...`)

```bash
echo "SLACK_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL" >> .env
echo "SLACK_ALERT_CHANNEL=#portal-alerts" >> .env
```
