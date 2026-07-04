---
id: unit-HOWTO-endpoints
kind: why
title: "HOWTO \u2014 Endpoints"
sources:
- type: design
  path: docs/HOWTO.md
  section: Endpoints
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.861071
updated_at: 1783195000.861071
---


| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health check |
| GET | `/metrics` | Prometheus metrics (text format) |
| GET | `/v1/models` | List all workspaces and personas |
| POST | `/v1/chat/completions` | Send messages, stream or blocking |
