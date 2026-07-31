---
id: unit-model-catalog-granite4-1-30b-ctx16k
kind: what
title: "MODEL_CATALOG \u2014 `granite4.1:30b-ctx16k`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 48aa40a11f2b
  section: '`granite4.1:30b-ctx16k`'
last_generated_commit: 48aa40a11f2b
confidence: high
tags:
- docs
created_at: 1785465745
updated_at: 1785465745
---

Context-capped derived tag of `granite4.1:30b` (`PARAMETER num_ctx 16384` baked in via `portal models apply-params`, P5-SEC-BENIGN-CORPUS-001 / Ollama 0.31 num_ctx-default fix). Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`, so capping context per-workspace requires a derived model tag rather than a request option. See base model's own catalog entry for full model detail; this entry exists only to satisfy backends.yaml/MODEL_CATALOG.md parity (test_model_catalog_parity.py).
