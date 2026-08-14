---
id: unit-model-catalog-omnicoder2-9b-q4-k-m-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `omnicoder2:9b-q4_k_m-ctx8k`"
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
created_at: 1784946220.655354
updated_at: 1784946220.655354
---

`omnicoder2:9b-q4_k_m-ctx8k` is the derived tag of `omnicoder2:9b-q4_k_m` with `PARAMETER num_ctx 8192` baked in via the `apply-params` command, required because Ollama's `/v1/chat/completions` drops request-time `options.num_ctx`. `config/backends.yaml` registers it in `group: coding` with `supports_tools: true` (the general-group entry carries the untagged base only). `config/portal.yaml` sets it as the auto-coding `uncensored` variant `model_hint` with `context_limit: 8192`, so the one-shot uncensored codegen lane runs on the capped id. Base model detail lives in the parent unit.

## Why

The ctx8k variant is the tag the auto-coding uncensored lane actually serves, so the grounding is the coding-group registration plus the uncensored variant's `model_hint` and `context_limit`. Stating that general carries only the untagged id explains why the derived tag is absent there. The bake-in mechanism is kept because the endpoint cannot take the context bound per request.
