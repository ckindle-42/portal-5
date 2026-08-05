---
id: unit-alerts-alert-thresholds
kind: what
title: "ALERTS \u2014 Alert Thresholds"
sources:
- type: code
  path: portal/platform/inference/notifications/dispatcher.py
- type: code
  path: .env.example
- type: code
  path: portal/platform/inference/cluster_backends.py
last_generated_commit: ca0f99d64c0644df1d5fc30674b6c476fceb1a42
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5486562
updated_at: 1784946220.5486562
---

Two behaviors govern when operational alerts fire. `ALERT_BACKEND_DOWN_THRESHOLD`, default three, counts consecutive unhealthy health cycles before a per-backend down event fires; the health loop runs roughly every thirty seconds. The all-backends-down alert is not tunable: the threshold checker always runs with `alert_all_down` true, and the `ALERT_NO_HEALTHY_BACKENDS` variable shipped in `.env.example` and forwarded by compose is never read by any code, so it has no effect.

## Why

Thresholds exist to suppress flapping: a single missed health check should not page anyone, and firing only at the transition boundary keeps alert volume bounded. The dead all-backends-down toggle deserves documentation precisely because it looks authoritative while the hardcoded default in the checker is what actually governs the whole-fleet path.
