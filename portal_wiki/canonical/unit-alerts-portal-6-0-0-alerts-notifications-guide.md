---
id: unit-alerts-portal-6-0-0-alerts-notifications-guide
kind: what
title: "ALERTS \u2014 Portal 6.0.0 \u2014 Alerts & Notifications Guide"
sources:
- type: code
  path: portal/platform/inference/notifications/dispatcher.py
- type: code
  path: portal/platform/inference/router/lifespan.py
- type: code
  path: portal/platform/inference/notifications/channels/__init__.py
last_generated_commit: ca0f99d64c0644df1d5fc30674b6c476fceb1a42
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5440252
updated_at: 1784946220.5440252
---

The notification layer offers five independently configurable channels — Slack, Telegram, Email, Pushover, and Webhook — all fed by a single dispatcher. Operational alerts fire on backend health transitions, and a daily usage summary runs once per day on a schedule. The whole subsystem stays off until `NOTIFICATIONS_ENABLED` is true, and channels only register when the master switch is on, so the default install sends nothing anywhere.

## Why

A single dispatcher fanning out to pluggable channels keeps delivery consistent across very different providers while making each one optional, so a stack that only uses email never has to think about Telegram. Disabled-by-default preserves the project's zero-config promise and forces an explicit choice before any external endpoint receives traffic.
