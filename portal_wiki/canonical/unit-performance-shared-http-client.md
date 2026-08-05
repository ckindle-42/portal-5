---
id: unit-performance-shared-http-client
kind: what
title: "PERFORMANCE \u2014 Shared HTTP Client"
sources:
- type: code
  path: portal/platform/inference/router/lifespan.py
- type: code
  path: portal/platform/inference/router/routing.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.509588
updated_at: 1784946220.509588
---

The pipeline creates one `httpx.AsyncClient` at startup in `portal/platform/inference/router/lifespan.py`, configured with `httpx.Timeout(600.0, connect=5.0)` and `httpx.Limits(max_keepalive_connections=20, max_connections=100)`. That client is then propagated to the modules that need it — routing (`_route_with_llm`), streaming, and the council — via direct assignment of `_http_client` at lifespan setup, so every backend request shares the same connection pool.

The LLM intent router uses this shared client rather than creating per-request clients, with the shorter router timeout enforced by `asyncio.wait_for` wrapping the call instead of a second client built for the router's millisecond budget. This keeps one pool for all backend traffic while still letting the router fail fast.

## Why

Connection pooling matters because the pipeline talks to local Ollama backends on the same host, and opening a fresh connection per request would trade away keepalive reuse on every inference call. The design also reconciles two conflicting timeout needs without duplicating the client: inference wants a long body timeout for cold model loads, while the LLM router needs to fail within its configured millisecond budget. Sharing the pool and layering the fast-fail above it with a wait-for is what makes both requirements hold at once.
