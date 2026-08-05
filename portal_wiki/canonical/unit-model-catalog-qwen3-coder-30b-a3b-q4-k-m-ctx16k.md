---
id: unit-model-catalog-qwen3-coder-30b-a3b-q4-k-m-ctx16k
kind: what
title: "MODEL_CATALOG \u2014 `qwen3-coder:30b-a3b-q4_K_M-ctx16k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 778def71961fd1bb2f1088be9754388706facf7a
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.657137
updated_at: 1784946220.657137
---

`qwen3-coder:30b-a3b-q4_K_M-ctx16k` is the derived tag of `qwen3-coder:30b-a3b-q4_K_M` with `PARAMETER num_ctx 16384` baked in via the `apply-params` command, required because Ollama's `/v1/chat/completions` drops request-time `options.num_ctx`. `config/backends.yaml` registers it in `group: coding` with `supports_tools: true`; the `omlx-coding` `aliases` block maps it to the oMLX `Qwen3-Coder-30B-A3B-Instruct-4bit` model. `config/portal.yaml` pins it as the `auto-coding` workspace `model_hint` with `context_limit: 16384`, and the auto-bigfix workspace uses the same tag. Base model detail lives in the parent unit.

## Why

The ctx16k variant is the tag the auto-coding and auto-bigfix lanes actually serve, so the grounding is the coding-group registration plus those two `model_hint` pins with their matching `context_limit`. The omlx alias is recorded because it lets the same GGUF hint reach the oMLX backend. The bake-in mechanism is stated because the endpoint cannot take the context bound per request.
