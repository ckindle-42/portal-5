---
id: unit-model-catalog-granite-4-1-8b-mxfp8
kind: what
title: "MODEL_CATALOG \u2014 `granite-4.1-8b-mxfp8`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 0fec84d46a8898b1b5baf0508af1e25634b099af
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786316500.0
updated_at: 1786316500.0
---

`granite-4.1-8b-mxfp8` is the ~8-bit mxfp8 MLX conversion (nightmedia) of granite-4.1-8b served by the oMLX evaluation backend, substituted here (same substitution `TASK_DAILY_WORK_FLEET_SOAK_V1` documents) because the 4-bit `unsloth-granite-4.1-8b-mlx-oQ4` conversion 409s and won't load. `config/backends.yaml` registers it in the `omlx-reasoning` entry (group `reasoning`, `priority: 10`), mapped from the `auto-compliance` workspace's `granite4.1:8b-ctx16k` model_hint. Added alongside `DeepSeek-R1-0528-Qwen3-8B-4bit` for the same reason as `Tongyi-DeepResearch-30B-A3B-abliterated-4bit` (see that unit) — `auto-compliance` pins its own model_hint distinct from `auto-reasoning`'s. Live-audited via a direct `/v1/chat/completions` tool-call probe (clean structured `tool_calls`, `finish_reason: tool_calls`, no template/tokenizer defects).

## Why

Grounds the model to the `omlx-reasoning` multi-model registration and the `auto-compliance` alias that lets its existing GGUF hint reach oMLX unchanged. Notes the mxfp8 substitution reason so a future session doesn't re-attempt the known-broken 4-bit conversion.
