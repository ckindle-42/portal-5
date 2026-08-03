---
id: unit-persona-matrix-ollama-client
kind: mixed
title: "Persona matrix Ollama client \u2014 pipeline-bypassing probe"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/ollama_client.py
  commit: 7954fafc
last_generated_commit: 7954fafc
claims: []
confidence: high
tags:
- authored-v1
- eval
- persona-matrix
created_at: 1785796995.099793
updated_at: 1785796995.099793
---

`ollama_client.py` is the raw Ollama HTTP client for the persona matrix: it
pins models in the request body to bypass the portal pipeline at :9099, so the
harness tests raw model behaviour independent of routing logic. It also holds
the admission helpers (`_ollama_unload` with cooldown) that mirror the
`bench_tps.py` memory-discipline pattern.

## Why

Bypassing the pipeline is the point: the matrix is asking "what can this
model do for this persona", not "does routing send this persona here". If the
harness went through the pipeline, a routing bug would masquerade as a model
capability gap (or hide one). The memory-discipline helpers exist because a
sweep loads and evicts models repeatedly, and unloading without a cooldown
causes Ollama to thrash — the same lesson `bench_tps.py` encoded.

## Interfaces

`_chat_direct` sends a raw completion request with the model pinned;
`_audit_tool_support` and `run_audit_tools` probe whether a model supports
the tool-call convention; `_ollama_unload` evicts a model with the cooldown.

## Gotchas

Because the client bypasses the pipeline, it bypasses the pipeline's
security and tool gating too — this client is for bench harnesses only, not
for serving user traffic.
