---
id: unit-router-init
kind: mixed
title: "Router subpackage \u2014 pipeline request engine split"
sources:
- type: code
  path: portal/platform/inference/router/__init__.py
  commit: a234187e
last_generated_commit: a234187e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798034.6191201
updated_at: 1785798034.6191201
---

The router subpackage is the actual request-handling engine of the pipeline,
split out of the monolithic `router_pipe` shim into focused modules: app
wiring, auth, concurrency, routing, streaming, tools, pre-injection, state,
metrics, power, and the Anthropic compatibility layer.

## Why

The split exists because the pipeline grew past a single file — routing
policy, streaming transport, and concurrency are three different concerns
that a monolith kept tangled. The separation mirrors the rule set: streaming
is pure bytes-in/SSE-out with no policy, routing owns the workspace decision,
workspaces owns the catalog, and each module states explicitly what it may
not import (streaming never imports router_pipe, routing never imports
router_pipe). That import discipline is what lets each module be tested in
isolation.

## Interfaces

The subpackage hosts `app` (the FastAPI entry), the routing/streaming/tools
engine, and the supporting modules. `router_pipe` re-exports the historical
surface from here.

## Gotchas

The import boundaries are the contract — a module that starts importing
`router_pipe` breaks the isolation the split exists to create.
