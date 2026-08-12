---
id: unit-model-catalog-lfm2-5-8b-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `lfm2.5:8b-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: a23f47b3e687df1693600eeea5b4f3f381b9da20
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.65502
updated_at: 1784946220.65502
---

`lfm2.5:8b-ctx8k` is the derived tag of `lfm2.5:8b` with `PARAMETER num_ctx 8192` baked in via the `apply-params` command, needed because Ollama's `/v1/chat/completions` drops request-time `options.num_ctx`. `config/backends.yaml` lists it in `group: general` and `group: security` with `supports_tools: true`, mirroring its parent. `config/portal.yaml` makes it the `auto-music` workspace `model_hint` with `context_limit: 8192`, so music generation runs against the capped tag rather than the full-context base. Base model detail lives in the parent unit.

## Why

The ctx8k variant is the tag the music lane actually serves, so the grounding is the two group registrations plus the auto-music model_hint and its matching context_limit. Keeping the parent cross-listing explicit explains why both groups carry the same tool flag. The baked-cap mechanism is stated because the endpoint cannot take the bound at request time.
