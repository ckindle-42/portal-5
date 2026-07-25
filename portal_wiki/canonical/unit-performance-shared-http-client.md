---
id: unit-performance-shared-http-client
kind: what
title: "PERFORMANCE \u2014 Shared HTTP Client"
sources:
- type: doc
  path: docs/PERFORMANCE.md
  commit: 05e42ec2
  section: Shared HTTP Client
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.509588
updated_at: 1784946220.509588
---

All backend requests use a single `httpx.AsyncClient` with connection pooling (20 keepalive, 100 max connections). The LLM router also uses this shared client instead of creating per-request clients.
