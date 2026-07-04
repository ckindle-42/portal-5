---
id: unit-PERFORMANCE-shared-http-client
kind: why
title: "PERFORMANCE \u2014 Shared HTTP Client"
sources:
- type: design
  path: docs/PERFORMANCE.md
  section: Shared HTTP Client
last_generated_commit: ''
confidence: high
tags:
- docs
- PERFORMANCE
created_at: 1783195000.8803682
updated_at: 1783195000.8803682
---

All backend requests use a single `httpx.AsyncClient` with connection pooling (20 keepalive, 100 max connections). The LLM router also uses this shared client instead of creating per-request clients.
