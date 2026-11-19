---
id: unit-HOWTO-prometheus-is-scraping-the-pipeline
historical: true
kind: why
title: "HOWTO \u2014 Prometheus is scraping the pipeline"
sources:
- type: design
  path: docs/HOWTO.md
  section: Prometheus is scraping the pipeline
confidence: high
tags:
- docs
- HOWTO

---

curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep portal-pipeline
