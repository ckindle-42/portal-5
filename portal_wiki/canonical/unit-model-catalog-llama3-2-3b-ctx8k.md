---
id: unit-model-catalog-llama3-2-3b-ctx8k
kind: what
title: "MODEL_CATALOG — `llama3.2:3b-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: f06ae3ff0835dd30c220449f6cf4f9ff2ebad233
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1785953825.388067
updated_at: 1785953825.388067
---

`llama3.2:3b-ctx8k` is a `-ctx8k`-tagged Ollama variant of `llama3.2:3b` (registered `config/backends.yaml`, `general` group, `supports_tools: true`), created via `ollama create` with a Modelfile-baked `PARAMETER num_ctx 8192`. It exists solely for `tests/benchmarks/bench_omlx_v3.py`'s shootout gate — Ollama's `/v1/chat/completions` endpoint silently ignores a runtime `options.num_ctx` override (verified live, Ollama 0.32.5), so a real context cap requires this baked-tag mechanism, matching every other `-ctxNk` model in the catalog. Not referenced by any `config/portal.yaml` workspace.

## Why

Discovered while building a fair oMLX-vs-Ollama multi-model bake-off: the bare `llama3.2:3b` tag was loading at its full 131072-token context regardless of any per-request cap, ballooning memory far beyond what a 900-4096 token test prompt needed. This tag gives the bench harness the same working context-control mechanism production workspaces already rely on.
