---
id: unit-alerts-slack
kind: what
title: "ALERTS \u2014 Slack"
sources:
- type: doc
  path: docs/ALERTS.md
  commit: 05e42ec2
  section: Slack
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5462432
updated_at: 1784946220.5462432
---

1. Create an Incoming Webhook at [https://api.slack.com/messaging/webhooks](https://api.slack.com/messaging/webhooks)
2. Copy the webhook URL (e.g. `https://hooks.slack.com/services/...`)

```bash
echo "SLACK_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL" >> .env
echo "SLACK_ALERT_CHANNEL=#portal-alerts" >> .env
```
