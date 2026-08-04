---
id: unit-performance-llm-router-warmup-at-startup
kind: what
title: "PERFORMANCE \u2014 LLM Router Warmup at Startup"
sources:
- type: code
  path: portal/platform/inference/router/lifespan.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.509268
updated_at: 1784946220.509268
---

`_warmup_llm_router()` in `portal/platform/inference/router/lifespan.py` fires at pipeline startup (as a background task from `_run_startup_warmups`) to pre-load the LLM intent-classifier model into Ollama before the first `auto`-routed request arrives. It posts a minimal `num_predict: 1` generate call to `${LLM_ROUTER_OLLAMA_URL}/api/generate`.

The load-bearing option is `keep_alive: -1` sent as a JSON integer. Ollama 0.30.8+ rejects the string form `"-1"`, so the payload pins the classifier model in memory indefinitely rather than letting a larger inference model evict it. `options.num_ctx` is set to `2048` to match the routing call in `_route_with_llm`, preventing the warmup from reserving tens of GiB via an over-wide context window. The warmup is skipped entirely when `LLM_ROUTER_ENABLED=false` — those deployments fall back to `_detect_workspace` keyword scoring and need no pin.

## Why

Every request that routes through the `auto` workspace first asks the classifier model for a routing decision, so a cold classifier adds a full model load to the first user request even when the inference model is already warm. Warming up alone is not enough — without a persistent pin the classifier is evicted the moment a large inference model loads, returning the deployment to a cold load on the next request. The integer keep-alive, the matched context window, and the feature-flag gate are the three knobs that make residency durable instead of a one-shot preload.
