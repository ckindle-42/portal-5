---
id: unit-router-context-inject
kind: mixed
title: "Router context inject \u2014 proactive memory/knowledge grounding"
sources:
- type: code
  path: portal/platform/inference/router/context_inject.py
  commit: a234187e
last_generated_commit: a234187e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798064.1881511
updated_at: 1785798064.1881511
---

`context_inject.py` implements proactive context injection and salient
memory write-back: it calls the tools the model already has — `recall`,
`kb_search`, `remember` — *before* the request, so grounding and persistence
no longer depend on the model choosing to call them.

## Why

A model that is not told to recall context will not recall it. The proactive
injection design makes grounding deterministic instead of model-dependent: if
the feature is enabled for the workspace, the injector fetches relevant
memories and knowledge and inserts them into the request's system message,
regardless of what the model would have chosen to do. It mirrors the
LLM-router design (env flag plus per-workspace opt-in, a short hard timeout
so a recall that hangs cannot stall the request path) and the snippet-shape
flattening is what the drift tests pin.

## Interfaces

`_extract_snippets` flattens tool result shapes; `_inject_context_block`
merges snippets into the system message; the recall path respects the
feature flag and the `_AUTO_MEMORY_ENABLED` switch.

## Gotchas

The hard timeout is essential — a proactive recall that takes the full
dispatch timeout would add that latency to every request, which is why the
injector wraps its calls in a much shorter `asyncio.wait_for`.
