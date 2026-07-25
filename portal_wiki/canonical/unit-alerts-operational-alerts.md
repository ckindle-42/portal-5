---
id: unit-alerts-operational-alerts
kind: what
title: "ALERTS \u2014 Operational Alerts"
sources:
- type: doc
  path: docs/ALERTS.md
  commit: 05e42ec2
  section: Operational Alerts
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.545603
updated_at: 1784946220.545603
---

Fired immediately when a threshold is crossed:

| Event | Trigger | Debounce |
|-------|---------|----------|
| `backend_down` | A backend fails `ALERT_BACKEND_DOWN_THRESHOLD` consecutive health checks | Yes — one alert per transition |
| `backend_recovered` | A previously-down backend passes a health check | Yes — one alert per transition |
| `all_backends_down` | Every backend is unhealthy simultaneously | Yes — fires once, clears on any recovery |
| `config_error` | `backends.yaml` missing or unparseable | No debounce |
