---
id: unit-known-limitations-router-model-eviction-single-request
kind: what
title: LLM Router Model Evicted by Single Inference Request (Resolved)
sources:
- type: code
  path: portal/platform/inference/router/lifespan.py
- type: code
  path: portal/platform/inference/router/routing.py
- type: code
  path: scripts/lib/util.sh
- type: code
  path: tests/unit/test_pipeline.py
- type: code
  path: portal/platform/inference/tool_preselect/preselector.py
- type: code
  path: portal/platform/inference/tool_preselect/cli_probe.py
last_generated_commit: f5987f1ea6b0cdb25b66e33a02b95183205d0605
claims: []
confidence: high
tags:
- known-limitations
- ollama
- resolved
- router
- verified-v1
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
- **2026-07-30 follow-up — the Ollama upgrade was necessary but not
  sufficient**: a live reproduction on this same `v0.32.5` host still evicted
  the router under real `auto`-routed traffic. Root cause was a second,
  distinct bug living in the same file: `_warmup_llm_router` and
  `_warmup_auto_model` (`lifespan.py`) both pin their model with
  `keep_alive: -1` but omitted `options.num_ctx`. Ollama then defaults the
  warmed runner's reserved context to the model's full context window
  multiplied by `OLLAMA_NUM_PARALLEL` slots (`4`) — for the router
  (`gemma-4-E4B`, 131072 max context) that is `131072 x 4 = 524288` tokens of
  reserved KV-cache, tens of GiB, for a 3B-class model. `_warmup_auto_model`
  had the identical gap warming `baronllm:q6_k` (also 131072 max context, no
  Modelfile cap), pinned forever with no cap at all. Either reservation alone
  is large enough to force the scheduler to evict everything else on the next
  model load — this is what reproduced live even after the version fix.
- **Fix**: both warmup calls now set `options.num_ctx` — `2048` for the
  router (matching the real classification call in `_route_with_llm`,
  `routing.py`) and `8192` for the auto-model warmup (matching the `auto`
  workspace's `context_limit`). Regression tests:
  `TestRouterWarmupContext::test_warmup_sets_same_num_ctx_as_routing_call` and
  `::test_auto_model_warmup_caps_num_ctx` in `tests/unit/test_pipeline.py`.
- **Live re-verification**: after rebuilding and restarting
  `portal5-pipeline`, `/api/ps` showed the router (2048 ctx), `baronllm`
  (8192 ctx), and the inference model (8192 ctx) all resident simultaneously
  across three consecutive live `auto`-routed `/v1/chat/completions`
  requests — no eviction.
- **Not isolated — two more sites fixed the same way**:
  `tool_preselect/preselector.py` and `tool_preselect/cli_probe.py` had the
  same missing-`num_ctx` shape (lower severity — `keep_alive: "5m"`
  self-expiring rather than `-1` permanent pin, and `preselector.py` has no
  call sites in the live request path as of this check, per
  `handlers.py`/`non_streaming.py`/`validation.py`). Both now set
  `options.num_ctx` (`4096`) on their `/api/generate` payloads. Regression
  tests: `TestOllamaOutcomes::test_payload_caps_num_ctx` in
  `portal/platform/inference/tool_preselect/tests/test_preselector.py`.
  `cli_probe.py` is operator-invoked only, no automated coverage needed.

## Why

The router warmup pins the model with `keep_alive: -1`, which is load-bearing: without it the router re-cold-loads on every heavy inference request. But the same pin becomes a memory bug when `options.num_ctx` is omitted, because Ollama then reserves the model's full context window times the parallel slots — tens of GiB for a small model — which forces the scheduler to evict the router it was trying to keep warm. Matching the warmup context to the real routing call and the workspace limit is what makes the pin actually safe.
