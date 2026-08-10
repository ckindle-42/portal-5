---
id: unit-model-catalog-llama3-2-3b-instruct-q8-0-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `llama3.2:3b-instruct-q8_0-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 5d5f217e3cd2b239cd1a8444769243ea0a3f752e
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1785953825.388067
updated_at: 1785957400.0
---

`llama3.2:3b-instruct-q8_0-ctx8k` is a `-ctx8k`-tagged Ollama variant of `llama3.2:3b-instruct-q8_0` (registered `config/backends.yaml`, `general` group, `supports_tools: true`, live-audited via `_audit_tools_probe`), created via `ollama create` with a Modelfile-baked `PARAMETER num_ctx 8192`. It exists solely for `tests/benchmarks/bench_omlx_v3.py`'s shootout gate — Ollama's `/v1/chat/completions` endpoint silently ignores a runtime `options.num_ctx` override (verified live, Ollama 0.32.5), so a real context cap requires this baked-tag mechanism, matching every other `-ctxNk` model in the catalog. Not referenced by any `config/portal.yaml` workspace.

## Why

Discovered while building a fair oMLX-vs-Ollama multi-model bake-off: the bare `llama3.2:3b` tag was loading at its full 131072-token context regardless of any per-request cap. Superseded an earlier `llama3.2:3b-ctx8k` (Q4_K_M) tag: a settings-parity audit found oMLX's counterpart (`Llama-3.2-3B-Instruct-8bit`) runs at 8-bit precision (3.6GB) while the default Ollama pull is Q4_K_M (2.0GB) — a real, unmatched ~2x precision gap. This tag uses `llama3.2:3b-instruct-q8_0` (3.4GB, Q8_0) instead, matching oMLX's bit-width class for a genuine apples-to-apples comparison.
