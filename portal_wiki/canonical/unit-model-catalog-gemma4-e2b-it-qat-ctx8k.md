---
id: unit-model-catalog-gemma4-e2b-it-qat-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:e2b-it-qat-ctx8k`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`gemma4:e2b-it-qat-ctx8k`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.645519
updated_at: 1784946220.645519
---

Context-capped derived tag of `gemma4:e2b-it-qat` (`PARAMETER num_ctx 8192` baked in via `portal models apply-params`, TASK-SEC-LIVE-EXEC / Ollama 0.31 num_ctx-default fix). Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`, so capping context per-workspace requires a derived model tag rather than a request option. See base model's own catalog entry for full model detail; this entry exists only to satisfy backends.yaml/MODEL_CATALOG.md parity (test_model_catalog_parity.py).
