---
id: unit-model-catalog-hf-co-bartowski-huihui-ai-qwen3-coder-next-abliterated-gguf-q4-k-m-ctx64k
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M-ctx64k`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M-ctx64k`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.647757
updated_at: 1784946220.647757
---

Context-capped derived tag of `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M` (`PARAMETER num_ctx 65536` baked in via `portal models apply-params`, TASK-SEC-LIVE-EXEC / Ollama 0.31 num_ctx-default fix). Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`, so capping context per-workspace requires a derived model tag rather than a request option. See base model's own catalog entry for full model detail; this entry exists only to satisfy backends.yaml/MODEL_CATALOG.md parity (test_model_catalog_parity.py).
