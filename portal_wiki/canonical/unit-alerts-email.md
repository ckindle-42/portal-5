---
id: unit-alerts-email
kind: what
title: "ALERTS \u2014 Email"
sources:
- type: code
  path: portal/platform/inference/notifications/channels/email.py
- type: code
  path: portal/platform/inference/router/lifespan.py
- type: code
  path: .env.example
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5472
updated_at: 1784946220.5472
---

The email channel requires `SMTP_HOST` and `EMAIL_ALERT_TO`; it also reports unconfigured when the aiosmtplib dependency is not importable. `SMTP_PORT` defaults to 587 and `SMTP_FROM` to portal@portal.local. Port 465 selects implicit TLS with a default security context; any other port enables STARTTLS. Username and password are optional and are only sent when provided.

## Why

Two transport modes exist because providers split between implicit TLS on port 465 and STARTTLS on 587, and a single send path cannot serve both. Making the recipient mandatory and the credentials optional keeps the channel usable for an internal relay while still supporting authenticated providers such as Gmail, whose two-factor users need an app password.
