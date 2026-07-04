---
id: unit-HOWTO-alert-types
kind: why
title: "HOWTO \u2014 Alert types"
sources:
- type: design
  path: docs/HOWTO.md
  section: Alert types
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.856995
updated_at: 1783195000.856995
---


| Event | When it fires |
|-------|---------------|
| `backend_down` | A backend fails N consecutive health checks (default: 3) |
| `backend_recovered` | A previously-down backend comes back |
| `all_backends_down` | Every backend is unhealthy simultaneously |
| `config_error` | `backends.yaml` is missing or unparseable |
| `daily_summary` | Once per day at configured hour (default: 09:00 UTC) |
