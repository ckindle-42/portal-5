---
id: unit-known-limitations-router-model-eviction-single-request
kind: what
title: "LLM Router Model Evicted by Single Inference Request (Open \u2014 Root Cause\
  \ Unconfirmed)"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  section: "LLM Router Model Evicted by Single Inference Request (Open \u2014 Root\
    \ Cause Unconfirmed)"
- type: code
  path: portal/platform/inference/router/lifespan.py
last_generated_commit: ''
confidence: high
tags:
- known-limitations
- router
- ollama
- open
created_at: 1785451451.3742568
updated_at: 1785451451.3742568
---

- **ID**: P5-ROUTER-EVICTION-001
- **Status**: OPEN — root cause unconfirmed. Do not treat as accepted/wontfix.
- **Description**: The LLM intent-router model (`LLM_ROUTER_MODEL`), loaded with
  `keep_alive: -1` specifically to stay pinned in memory (see
  `_warmup_llm_router` in `lifespan.py`), gets evicted by Ollama after exactly
  **one** subsequent completion request to a different inference model —
  reproduced twice in a clean, minimal test: fresh pipeline restart → router
  model confirmed loaded and pinned "Forever" via `ollama ps` → one single
  `/v1/chat/completions` request → `ollama ps` shows only the inference model,
  router gone. Both models were ~5-6GB (≈11GB combined), nowhere near this
  host's 64GB unified memory or a 5-model `OLLAMA_MAX_LOADED_MODELS` cap.
- **Ruled out**: `OLLAMA_MAX_LOADED_MODELS` was found completely absent from
  the actual host-native Ollama service's launchd plist
  (`/Library/LaunchDaemons/com.portal5.ollama.plist`) — the `.env` value only
  ever applied to the unused, optional Dockerized Ollama profile. This was a
  real, separate config gap and has been fixed (plist now sets
  `OLLAMA_MAX_LOADED_MODELS=5` and `OLLAMA_NUM_PARALLEL=4`, matching `.env`).
  **Fixing it did not resolve the eviction** — reproduced again afterward with
  only 2 of 5 slots in use. Not a testing-methodology artifact either: the
  reproduction is a single clean two-step transition (restart, one request),
  not an accumulation of the session's earlier heavy multi-model churn.
- **Impact**: Every real "auto"-routed request pays the LLM router's full
  cold-load latency (2.7-4s observed) rather than the documented ~840ms warm
  figure, because the router is never actually warm when a real request
  arrives — the previous request's inference model always evicted it. This
  is a real, live tax on router accuracy/latency tradeoffs project-wide, and
  a plausible contributing factor (not sole cause) in some of the extreme
  multi-thousand-second "backend instability" retry patterns observed during
  the v8.0.0 UAT sweep on `auto`-prefixed workspaces.
- **Not accepted as a hardware limitation**: Apple Silicon's unified memory
  architecture should not require this behavior at these memory sizes.
  Suspected but unconfirmed: an Ollama/Metal backend GPU-residency
  constraint that evicts prior models on new-model load regardless of
  `keep_alive` or slot-count settings — needs direct investigation (GPU
  memory telemetry during the transition, Ollama scheduler source/issue
  tracker, or a version bisect) before being called root-caused.
- **Mitigation shipped**: None yet — `LLM_ROUTER_TIMEOUT_MS` is set to
  `1000ms` (the project's own bench-validated value for a *warm* router),
  which does not cover the observed cold-load time. Raising the timeout
  further would mask the real problem with added latency on every request;
  not done pending root cause.
- **Next action**: Investigate Ollama's Metal backend model-residency/eviction
  behavior directly (e.g. instrumented GPU memory sampling across a
  load/evict transition, or an Ollama version bisect) rather than tuning
  config further.
