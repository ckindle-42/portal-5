---
id: unit-ALERTS-email
kind: why
title: "ALERTS \u2014 Email"
sources:
- type: design
  path: docs/ALERTS.md
  section: Email
last_generated_commit: ''
confidence: high
tags:
- docs
- ALERTS
created_at: 1783195000.819978
updated_at: 1783195000.819978
---


Any SMTP provider works (Gmail, Mailgun, SendGrid, etc.):

```bash
echo "SMTP_HOST=smtp.example.com" >> .env
echo "SMTP_PORT=587" >> .env
echo "SMTP_USER=your-username" >> .env
echo "SMTP_PASSWORD=your-password" >> .env
echo "SMTP_FROM=portal@portal.local" >> .env
echo "EMAIL_ALERT_TO=admin@portal.local" >> .env
```

For Gmail with 2FA, use an [App Password](https://support.google.com/accounts/answer/185833).
