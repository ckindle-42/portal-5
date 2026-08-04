---
id: unit-alerts-1-enable-notifications
kind: what
title: "ALERTS \u2014 1. Enable notifications"
sources:
- type: code
  path: .env.example
- type: code
  path: portal/platform/inference/notifications/dispatcher.py
- type: code
  path: portal/platform/inference/router/lifespan.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.54497
updated_at: 1784946220.54497
---

Notifications are disabled by default. The dispatcher reads `NOTIFICATIONS_ENABLED` at construction and refuses to register any channel while it is false, and the pipeline lifespan never even imports the notifications package unless the variable is truthy. Setting it to true in `.env` and restarting the pipeline container activates the subsystem; every channel is then independently optional, and a channel without its own variables stays silent.

## Why

A master switch means an operator who wants only Slack does not have to reason about five separate toggles, and a misconfigured channel cannot take the whole subsystem down at registration time. Disabled-by-default keeps a zero-config install quiet, so the first alert an operator sees is one they explicitly opted into rather than surprise traffic to an external service.
