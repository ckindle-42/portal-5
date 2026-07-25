---
id: unit-alerts-email
kind: what
title: "ALERTS \u2014 Email"
sources:
- type: doc
  path: docs/ALERTS.md
  commit: 05e42ec2
  section: Email
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5472
updated_at: 1784946220.5472
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
