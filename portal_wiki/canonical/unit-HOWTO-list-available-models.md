---
id: unit-HOWTO-list-available-models
kind: why
title: "HOWTO \u2014 List available models"
sources:
- type: design
  path: docs/HOWTO.md
  section: List available models
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.86148
updated_at: 1783195000.86148
---


```bash
curl -s http://localhost:9099/v1/models \
  -H "Authorization: Bearer $PIPELINE_API_KEY" \
  | python3 -m json.tool | grep '"id"'
