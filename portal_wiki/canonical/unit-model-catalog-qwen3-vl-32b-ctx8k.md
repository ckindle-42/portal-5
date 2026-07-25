---
id: unit-model-catalog-qwen3-vl-32b-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `qwen3-vl:32b-ctx8k`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`qwen3-vl:32b-ctx8k`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.658004
updated_at: 1784946220.658004
---

Context-capped derived tag of `qwen3-vl:32b` (`PARAMETER num_ctx 8192` baked in via `portal models apply-params`, TASK-SEC-LIVE-EXEC / Ollama 0.31 num_ctx-default fix). Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`, so capping context per-workspace requires a derived model tag rather than a request option. See base model's own catalog entry for full model detail; this entry exists only to satisfy backends.yaml/MODEL_CATALOG.md parity (test_model_catalog_parity.py).
