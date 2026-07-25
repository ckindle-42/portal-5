---
id: unit-ALERTS-operational-alerts
kind: why
title: "ALERTS \u2014 Operational Alerts"
sources:
- type: design
  path: docs/ALERTS.md
  section: Operational Alerts
last_generated_commit: ''
confidence: high
tags:
- docs
- ALERTS
created_at: 1783195000.819131
updated_at: 1783195000.819131
---


Fired immediately when a threshold is crossed:

| Event | Trigger | Debounce |
|-------|---------|----------|
| `backend_down` | A backend fails `ALERT_BACKEND_DOWN_THRESHOLD` consecutive health checks | Yes — one alert per transition |
| `backend_recovered` | A previously-down backend passes a health check | Yes — one alert per transition |
| `all_backends_down` | Every backend is unhealthy simultaneously | Yes — fires once, clears on any recovery |
| `config_error` | `backends.yaml` missing or unparseable | No debounce |
