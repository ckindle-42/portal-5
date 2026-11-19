---
id: unit-HOWTO-authentication
historical: true
kind: why
title: "HOWTO \u2014 Authentication"
sources:
- type: design
  path: docs/HOWTO.md
  section: Authentication
confidence: high
tags:
- docs
- HOWTO

---


All requests require `PIPELINE_API_KEY` from `.env` as a Bearer token:

```bash
PIPELINE_API_KEY=$(grep PIPELINE_API_KEY .env | cut -d= -f2)
```
