---
id: unit-router-preinject
kind: mixed
title: "Router preinject \u2014 persona/routing/vision pre-dispatch transforms"
sources:
- type: code
  path: portal/platform/inference/router/preinject.py
  commit: a234187e
last_generated_commit: a234187e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798099.78304
updated_at: 1785798099.78304
---

`preinject.py` is the pre-dispatch request-transform layer: it takes the
incoming request and applies context-aware mutations — persona-to-workspace
resolution, auto routing, vision fallback, temporal context, system-prompt
append, and file-attachment normalisation — before dispatch to the backend.

## Why

The transforms are what make the pipeline persona-aware rather than a bare
model proxy. A request that arrives without a workspace hint gets one
resolved here (persona → workspace), a vision workspace that received no
image falls back to the reasoning workspace, and the temporal context and
attachment normalisation happen before the model sees anything. Centralising
them means the dispatch path stays clean and each transform is testable in
isolation — and the auto-routing resolution here is what the drift tests for
the `_resolve_auto_routing` path pin.

## Interfaces

`_resolve_persona_workspace`, `_resolve_auto_routing`,
`_resolve_vision_fallback`, `_inject_temporal_context`,
`_inject_system_prompt_append`, and `_inject_attached_files` are the
transforms, applied in the documented order before dispatch.

## Gotchas

Order matters: persona resolution must precede auto-routing (the resolved
workspace feeds the router), and the transforms must be idempotent enough
that re-injecting on a retry does not duplicate context.
