---
id: unit-HOWTO-prometheus-is-scraping-the-pipeline
kind: why
title: "HOWTO \u2014 Prometheus is scraping the pipeline"
sources:
- type: design
  path: docs/HOWTO.md
  section: Prometheus is scraping the pipeline
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.864245
updated_at: 1783195000.864245
---

curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep portal-pipeline
