---
id: unit-inference-router-pipe
kind: mixed
title: "Inference router_pipe \u2014 OWUI contract compatibility shim"
sources:
- type: code
  path: portal/platform/inference/router_pipe.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
created_at: 1785797760.483242
updated_at: 1785797760.483242
---

`router_pipe.py` is the backwards-compatibility shim that keeps Open
WebUI's contract alive: the pipeline manifest references
`portal.platform.inference.router_pipe.app`, so this module re-exports `app`
and every symbol downstream consumers historically imported, from the
canonical router subpackage.

## Why

The router was reorganised into `portal.platform.inference.router.*`, and a
reorg that breaks the entry point everyone imports is a reorg that ships
broken. The shim preserves the `router_pipe` name so OWUI's connection config
and any script importing `router_pipe.app` keep working while new code moves
to the canonical location. It is the documented pattern for a re-export
boundary: the shim exists only to bridge, and new imports should target the
router subpackage directly.

## Interfaces

Re-exports `app`, the Anthropic compat functions, auth, concurrency,
handlers, lifespan, metrics, routing, state, streaming, tools, validation,
and workspaces symbols — the full historical surface.

## Gotchas

The shim is deliberately frozen — new symbols should be added to the router
subpackage, not to this file, or the shim grows into a second home for the
pipeline's surface.
