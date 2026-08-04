---
id: unit-HOWTO-configure-channels
kind: why
title: "HOWTO \u2014 Configure channels"
sources:
- type: design
  path: docs/HOWTO.md
  section: Configure channels
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.85679
updated_at: 1783195000.85679
---


**Slack:**
```bash
SLACK_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_ALERT_CHANNEL=#portal-alerts
```

**Telegram (use a separate alert bot):**
```bash
TELEGRAM_ALERT_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_ALERT_CHANNEL_ID=-1001234567890
```

**Email:**
```bash
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-username
SMTP_PASSWORD=your-password
SMTP_FROM=portal@portal.local
EMAIL_ALERT_TO=admin@portal.local
```

**Pushover:**
```bash
PUSHOVER_API_TOKEN=your-app-token
PUSHOVER_USER_KEY=your-user-key
```
