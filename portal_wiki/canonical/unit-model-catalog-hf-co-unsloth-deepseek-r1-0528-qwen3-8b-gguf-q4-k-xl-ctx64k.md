---
id: unit-model-catalog-hf-co-unsloth-deepseek-r1-0528-qwen3-8b-gguf-q4-k-xl-ctx64k
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.650228
updated_at: 1784946220.650228
---

Context-capped derived tag of `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL` (`PARAMETER num_ctx 65536` baked in via `portal models apply-params`, TASK-SEC-LIVE-EXEC / Ollama 0.31 num_ctx-default fix). Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`, so capping context per-workspace requires a derived model tag rather than a request option. See base model's own catalog entry for full model detail; this entry exists only to satisfy backends.yaml/MODEL_CATALOG.md parity (test_model_catalog_parity.py).
