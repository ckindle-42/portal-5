---
id: unit-alerts-quick-start
kind: what
title: "ALERTS \u2014 Quick Start"
sources:
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: .env.example
- type: code
  path: portal/platform/inference/notifications/dispatcher.py
claims:
- probe: repo.path.exists
  path: portal/platform/inference/router/handlers.py
  equals: true
confidence: high
tags:
- docs
- verified-v1
---

Enabling alerts is a three-step process: set `NOTIFICATIONS_ENABLED` to true in `.env`, add at least one channel's variables, and restart the pipeline so the values are read at startup. To verify without waiting for an incident, POST to the `/notifications/test` endpoint, which dispatches a sample alert and a live summary and reports each channel's configured state in the response.

## Why

A test endpoint exists because alert wiring has too many silent-failure modes — bad tokens, unreachable endpoints, malformed headers — and discovering them during a real outage is the worst possible time. An explicit verification step turns configured from a hope into a checkable state before an operator walks away.
