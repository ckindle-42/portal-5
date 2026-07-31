---
id: unit-known-limitations-router-model-eviction-single-request
kind: what
title: LLM Router Model Evicted by Single Inference Request (Resolved)
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  section: LLM Router Model Evicted by Single Inference Request (Resolved)
- type: code
  path: portal/platform/inference/router/lifespan.py
- type: code
  path: scripts/lib/util.sh
- type: doc
  path: https://github.com/ollama/ollama/commit/9eef4a7195dc8ad246e697a5251a8df344a56880
  section: mlx keep loaded model memory resident
last_generated_commit: ''
confidence: high
tags:
- known-limitations
- router
- ollama
- resolved
created_at: 1785451451.3742568
updated_at: 1785458075
---

- **ID**: P5-ROUTER-EVICTION-001
- **Status**: RESOLVED 2026-07-30 — fixed upstream in the supported Ollama line and
  regression-probed on this host.
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
- **Root cause and upstream fix**: Ollama commit
  `9eef4a7195dc8ad246e697a5251a8df344a56880` ("mlx: keep loaded model memory
  resident"), released in `v0.32.4`, configures Metal residency after the MLX
  runner materializes model weights. This directly addresses the missing
  residency behavior suspected in the original finding. A version bisect was
  not performed, but the upstream change and the post-upgrade reproduction
  agree on the failure mechanism.
- **Regression proof**: On the current `v0.32.5` server, a clean
  router-load → `/v1/chat/completions` inference transition left both the
  5.3GB router model and a 5.6GB inference model present in `/api/ps`, each
  fully resident in Metal memory. Repeating through the OpenAI-compatible
  endpoint no longer evicts the router.
- **Repository fix**: Portal's Apple-Silicon launch preflight now treats
  Ollama `v0.32.4` as the supported minimum and warns before launch on older
  servers. The previous `0.30.7+` requirement allowed the known-bad residency
  behavior back into supported deployments.
- **No latency workaround added**: `LLM_ROUTER_TIMEOUT_MS` remains at the
  bench-validated warm-router value. The pipeline does not re-warm after every
  request or silently disable semantic routing; those mitigations would evict
  useful inference models or reduce routing accuracy.
