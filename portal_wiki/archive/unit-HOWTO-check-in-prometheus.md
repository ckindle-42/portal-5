---
id: unit-HOWTO-check-in-prometheus
historical: true
kind: why
title: "HOWTO \u2014 Check in Prometheus"
sources:
- type: design
  path: docs/HOWTO.md
  section: Check in Prometheus
confidence: high
tags:
- docs
- HOWTO

---


1. Open http://localhost:9090
2. Enter query: `rate(portal_requests_by_model_total[5m])`
3. Click "Execute"
