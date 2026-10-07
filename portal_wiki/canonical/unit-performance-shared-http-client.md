---
id: unit-performance-shared-http-client
kind: what
title: "PERFORMANCE \u2014 Shared HTTP Client"
sources:
- type: code
  path: portal/platform/inference/router/lifespan.py
- type: code
  path: portal/platform/inference/router/routing.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.509588
updated_at: 1784946220.509588
---

The pipeline creates one translated `httpx.AsyncClient` at startup in `portal/platform/inference/router/lifespan.py`, configured with `httpx.Timeout(600.0, connect=5.0)` and `httpx.Limits(max_keepalive_connections=20, max_connections=100)`. That client is propagated to routing, streaming, and the council for `/v1` backend traffic. Native MCP passthrough uses a second plain client with the same limits and timeout: it deliberately has no `OllamaNativeTransport`, so it can forward Ollama-native bytes without changing `think`, `images`, `format`, or response fields.

The LLM intent router uses the translated shared client rather than creating per-request clients, with the shorter router timeout enforced by `asyncio.wait_for` wrapping the call instead of a second client built for the router's millisecond budget. Its native Ollama requests are admitted and tracked by `LoadGuard` before the request is sent.

## Why

Connection pooling matters because the pipeline talks to local Ollama backends on the same host, and opening a fresh connection per request would trade away keepalive reuse on every inference call. The design also reconciles two conflicting timeout needs without duplicating the client: inference wants a long body timeout for cold model loads, while the LLM router needs to fail within its configured millisecond budget. Sharing the pool and layering the fast-fail above it with a wait-for is what makes both requirements hold at once.
