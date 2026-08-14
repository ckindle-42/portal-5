---
id: unit-model-catalog-qwen3-coder-30b-a3b-q4-k-m-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `qwen3-coder:30b-a3b-q4_K_M-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 64c5f5f41652bf67e97863ee1a6285289eaeea00
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.657608
updated_at: 1784946220.657608
---

`qwen3-coder:30b-a3b-q4_K_M-ctx8k` is the derived tag of `qwen3-coder:30b-a3b-q4_K_M` with `PARAMETER num_ctx 8192` baked in via the `apply-params` command, needed because Ollama's `/v1/chat/completions` discards request-time `options.num_ctx`. `config/backends.yaml` registers it in `group: coding` with `supports_tools: true`. `config/portal.yaml` pins it as the `auto-cad` workspace `model_hint` with `context_limit: 8192`, so parametric 3D-model generation runs against the capped tag rather than the full-context base. Parent model detail lives in the base unit.

## Why

The ctx8k variant is the tag the auto-cad lane serves, so the grounding is the coding-group registration plus the workspace `model_hint` and its matching `context_limit`. The single-group placement contrasts with the parent's general/coding split, which is why the tool flag here is simply true. The bake-in mechanism is kept because the endpoint cannot apply the context bound per request.
