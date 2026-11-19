---
id: unit-HOWTO-endpoints
historical: true
kind: why
title: "HOWTO \u2014 Endpoints"
sources:
- type: design
  path: docs/HOWTO.md
  section: Endpoints
confidence: high
tags:
- docs
- HOWTO

---


| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health check |
| GET | `/metrics` | Prometheus metrics (text format) |
| GET | `/v1/models` | List all workspaces and personas |
| POST | `/v1/chat/completions` | Send messages, stream or blocking |
