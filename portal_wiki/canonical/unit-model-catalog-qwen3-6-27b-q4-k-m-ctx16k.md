---
id: unit-model-catalog-qwen3-6-27b-q4-k-m-ctx16k
kind: what
title: "MODEL_CATALOG — `qwen3.6:27b-q4_K_M-ctx16k`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  section: '`qwen3.6:27b-q4_K_M-ctx16k`'
last_generated_commit: ''
confidence: high
tags:
- docs
created_at: 1785470000
updated_at: 1785470000
---

Context-capped derived tag of `qwen3.6:27b-q4_K_M` (`PARAMETER num_ctx 16384` baked in via `portal models apply-params`, P5-ROUTER-EVICTION-001 follow-up). `auto-council` was the only workspace with `context_limit` set but no baked `-ctx` tag; its base model's max context is 262144, so leaving it uncapped meant every real request reserved `262144 x OLLAMA_NUM_PARALLEL` tokens of KV-cache, large enough to evict the rest of the fleet. Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`, so capping context per-workspace requires a derived model tag rather than a request option. See base model's own catalog entry for full model detail; this entry exists only to satisfy backends.yaml/MODEL_CATALOG.md parity (test_model_catalog_parity.py).
