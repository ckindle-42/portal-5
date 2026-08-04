---
id: unit-router-routing
kind: mixed
title: "Router routing \u2014 LLM + keyword two-layer workspace resolution"
sources:
- type: code
  path: portal/platform/inference/router/routing.py
  commit: a234187e
last_generated_commit: a234187e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798105.731314
updated_at: 1785798105.731314
---

`routing.py` is the workspace router: it loads the routing descriptions and
examples, builds the router prompt, calls the LLM router model, and falls
back to weighted keyword scoring, resolving a workspace id from a message
list.

## Why

The two-layer routing design exists because both layers have failure modes
the other covers. The LLM router (a small classifier model) is accurate on
ambiguous language but costs ~840ms and can time out; the keyword scorer is
instant but blunt. The design runs the LLM first and falls back to keywords
on low confidence or timeout, so routing is never unavailable and never
purely heuristic. The `_http_client` injection is the boundary note: it is
set by `lifespan` after the shared client is created, and `None` until then —
so the router must never assume the client exists at import time.

## Interfaces

`_detect_workspace` is the entry that resolves a message list to a workspace
id; `_route_with_llm` is the LLM pass; the keyword tables
(`_CODING_KEYWORDS`, `_SPL_KEYWORDS`) and the classifier constants
(`_LLM_ROUTER_MODEL`) configure the fallback.

## Gotchas

The confidence floor is the fallback trigger — a router model that answers
with 0.4 confidence is ignored, because a confident keyword match is better
than a shaky model call.
