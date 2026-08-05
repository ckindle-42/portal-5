---
id: unit-alerts-fire-all-backends-down-immediately-when-all-backends-fail-default-true
kind: what
title: "ALERTS \u2014 Fire ALL_BACKENDS_DOWN immediately when all backends fail (default:\
  \ true)"
sources:
- type: code
  path: portal/platform/inference/notifications/dispatcher.py
- type: code
  path: portal/platform/inference/router/lifespan.py
- type: code
  path: .env.example
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: ca0f99d64c0644df1d5fc30674b6c476fceb1a42
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.549353
updated_at: 1784946220.549353
---

The all-backends-down alert fires the first time a health cycle finds every registered backend unhealthy, and only once: the `_alerted_all_down` latch holds until any backend recovers, then clears. Notably, `ALERT_NO_HEALTHY_BACKENDS` — the variable documented in `.env.example` and forwarded by the compose service — is never read anywhere; the checker's `alert_all_down` parameter defaults to true and the lifespan health callback always invokes it that way. Behavior is therefore fixed, not configurable.

## Why

A total outage is an emergency and should not wait for a debounce window or a configurable count, so the event is deliberately hardcoded on. Latching until recovery stops the thirty-second health loop from flooding channels with identical messages, and the inert variable is called out here so no operator trusts a toggle that silently does nothing.
