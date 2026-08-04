---
id: unit-HOWTO-authentication
kind: why
title: "HOWTO \u2014 Authentication"
sources:
- type: design
  path: docs/HOWTO.md
  section: Authentication
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.860851
updated_at: 1783195000.860851
---


All requests require `PIPELINE_API_KEY` from `.env` as a Bearer token:

```bash
PIPELINE_API_KEY=$(grep PIPELINE_API_KEY .env | cut -d= -f2)
```
