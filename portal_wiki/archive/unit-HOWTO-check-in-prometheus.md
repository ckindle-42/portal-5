---
id: unit-HOWTO-check-in-prometheus
kind: why
title: "HOWTO \u2014 Check in Prometheus"
sources:
- type: design
  path: docs/HOWTO.md
  section: Check in Prometheus
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.8637881
updated_at: 1783195000.8637881
---


1. Open http://localhost:9090
2. Enter query: `rate(portal_requests_by_model_total[5m])`
3. Click "Execute"
