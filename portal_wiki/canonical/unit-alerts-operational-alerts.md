---
id: unit-alerts-operational-alerts
kind: what
title: "ALERTS \u2014 Operational Alerts"
sources:
- type: code
  path: portal/platform/inference/notifications/dispatcher.py
- type: code
  path: portal/platform/inference/notifications/events.py
- type: code
  path: portal/platform/inference/router/lifespan.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.545603
updated_at: 1784946220.545603
---

Four alert events model the operational surface. `backend_down` and `backend_recovered` are transition pairs driven by the consecutive-failure counter. `all_backends_down` latches until any backend becomes healthy again. `config_error` is dispatchable through `check_config_error` but no call site invokes it today, so a missing or unparseable backends.yaml produces no alert. All events flow from the same threshold check that the health loop invokes after each cycle.

## Why

The event set matches what a stateless router can actually observe: per-backend and whole-fleet health transitions. Keeping the config error event available but unwired reflects that the pipeline currently fails loudly at startup instead of alerting, and stating that gap matters more than pretending a table row is exercised code.
