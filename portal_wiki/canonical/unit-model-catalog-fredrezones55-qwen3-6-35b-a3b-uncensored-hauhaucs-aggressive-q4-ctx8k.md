---
id: unit-model-catalog-fredrezones55-qwen3-6-35b-a3b-uncensored-hauhaucs-aggressive-q4-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.643863
updated_at: 1784946220.643863
---

Context-capped derived tag of `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4` (`PARAMETER num_ctx 8192` baked in via `portal models apply-params`, TASK-SEC-LIVE-EXEC / Ollama 0.31 num_ctx-default fix). Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`, so capping context per-workspace requires a derived model tag rather than a request option. See base model's own catalog entry for full model detail; this entry exists only to satisfy backends.yaml/MODEL_CATALOG.md parity (test_model_catalog_parity.py).
