---
id: unit-inference-init
kind: mixed
title: "Inference package \u2014 OpenAI-compatible router tier"
sources:
- type: code
  path: portal/platform/inference/__init__.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
created_at: 1785797736.850399
updated_at: 1785797736.850399
---

The inference package is the Portal 5 pipeline — the OpenAI-compatible
router that sits between Open WebUI and Ollama. It carries the pipeline's
version string and hosts the router subpackage where the actual request
handling lives.

## Why

The package boundary marks the inference tier: everything that serves chat
requests lives under it, and the independence rules forbid the MCP servers
and the wiki engine from importing it (and it from importing them). The
version string here is the pipeline's own, distinct from the fleet-wide
version.

## Interfaces

`__version__` only — the real surface is `router_pipe` (the app entry),
`config`, `sync_config`, and `tool_registry`.
