---
id: unit-HOWTO-list-available-models
historical: true
kind: why
title: "HOWTO \u2014 List available models"
sources:
- type: design
  path: docs/HOWTO.md
  section: List available models
confidence: high
tags:
- docs
- HOWTO

---


```bash
curl -s http://localhost:9099/v1/models \
  -H "Authorization: Bearer $PIPELINE_API_KEY" \
  | python3 -m json.tool | grep '"id"'
