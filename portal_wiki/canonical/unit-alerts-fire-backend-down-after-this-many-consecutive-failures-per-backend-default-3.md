---
id: unit-alerts-fire-backend-down-after-this-many-consecutive-failures-per-backend-default-3
kind: what
title: "ALERTS \u2014 Fire BACKEND_DOWN after this many consecutive failures per backend\
  \ (default: 3)"
sources:
- type: code
  path: portal/platform/inference/notifications/dispatcher.py
- type: code
  path: portal/platform/inference/notifications/events.py
- type: code
  path: .env.example
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.548993
updated_at: 1784946220.548993
---

`ALERT_BACKEND_DOWN_THRESHOLD` defaults to three consecutive failures. On every health-cycle callback the dispatcher bumps a per-backend failure counter for each unhealthy check and fires `backend_down` only when the counter equals the threshold; a healthy check resets the counter, and if the threshold had previously been reached it also emits `backend_recovered`. Resetting on recovery is what makes each alert fire once per transition rather than on every check.

## Why

Counting consecutive failures rather than firing on the first missed check absorbs the transient blips a warm model or a busy Ollama can produce. Firing exactly at the threshold and resetting on recovery bounds message volume to one per state change, which keeps a genuinely failing backend identifiable without drowning every channel in duplicate alerts.
