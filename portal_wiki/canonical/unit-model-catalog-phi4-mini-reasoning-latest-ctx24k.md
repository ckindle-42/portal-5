---
id: unit-model-catalog-phi4-mini-reasoning-latest-ctx24k
kind: what
title: "MODEL_CATALOG \u2014 `phi4-mini-reasoning:latest-ctx24k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 1ed83b22525c97ed996c835b7519e10c75d13ad0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.655746
updated_at: 1784946220.655746
---

`phi4-mini-reasoning:latest-ctx24k` is the derived tag of `phi4-mini-reasoning:latest` with `PARAMETER num_ctx 24576` baked in via the `apply-params` command, required because Ollama's `/v1/chat/completions` drops request-time `options.num_ctx`. `config/backends.yaml` registers it in `group: reasoning` with `supports_tools: false`, matching its parent. `config/portal.yaml` sets it as the `auto-math` workspace `model_hint` with `context_limit: 24576`, so the math lane runs on the capped tag. See the parent unit for the RL math-specialist background and the `:math` bench warning.

## Why

The ctx24k variant is the exact tag the auto-math lane serves, so the grounding is the reasoning-group registration plus the workspace `model_hint` and its matching `context_limit`. Keeping the supports_tools false flag explicit preserves the parent's non-tooling nature. The bake-in mechanism is stated because the endpoint cannot apply the context bound per request.
