---
id: unit-surface-router
kind: mixed
title: "Router subpackage \u2014 workspace routing, council quorum, request engine,\
  \ observability"
sources:
- type: code
  path: portal/platform/inference/router/*.py
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785885200.0
updated_at: 1785885200.0
---

The router subpackage is the pipeline's request-handling engine, split from the monolithic `router_pipe` shim into focused modules. The contract: `app` binds the routes and middleware uvicorn serves, `auth` gates chat and admin traffic with distinct bearer keys, and `concurrency` bounds Ollama load through three semaphore tiers inside a single-owner `RequestSlot`. Routing policy lives in `routing` with the `workspaces` catalog, `context_inject` grounds requests proactively, `preinject` applies persona and vision transforms pre-dispatch, and `state` persists telemetry without storing conversation. A `metrics` registry feeds power, monitor, and correlation observability, scraped by the Grafana stack; Anthropic compatibility, thinking normalisation, and council quorum complete the engine.

## Why

The split is architectural, not stylistic: routing policy, streaming transport, and concurrency are different concerns that a monolith kept tangled, and each module declares an import boundary (never `router_pipe`) so it can be tested in isolation. The load-bearing decisions baked in — admin keys stricter than the pipeline key, a quorum floor where abstentions count against the vote, pre-lowered keyword dictionaries keep fallback cheap, proactive recall behind a short hard timeout, and a startup warmup for the router model — trade latency for a property the serving path depends on.

## Interfaces

`app` re-exports the FastAPI entry; `WORKSPACES` drives routing and persona tool resolution; `_detect_workspace` resolves a message list to a workspace with `_KEYWORD_CACHE` fallback; `aggregate_opinions` enforces council quorum; `anthropic_to_openai_body` and `openai_stream_to_anthropic_sse` translate the Messages API; `strip_think` and `extract_think_inner` manage reasoning blocks; `get_metrics_summary` reads the shared `metrics` registry.

## Gotchas

The import boundaries are the contract — importing `router_pipe` breaks the isolation the split exists to create. `WORKSPACES` is built at import time, so config changes need a restart. Semaphore limits are per-process, not fleet-wide. `PROMETHEUS_MULTIPROC_DIR` must be set before `metrics` imports. `purge_memory` precedes the disruptive `restart_ollama`. Streaming stays pure transport with no policy; live-streaming and warmup units keep their own mandates.
