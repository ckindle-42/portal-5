---
id: unit-model-catalog-granite-4-1-30b-4bit
kind: what
title: "MODEL_CATALOG \u2014 `granite-4.1-30b-4bit`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: d19bcd41d50c690918807eab095f1f738f9798d5
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786316500.0
updated_at: 1786316500.0
---

`granite-4.1-30b-4bit` is the 4-bit MLX conversion (mlx-community) of granite-4.1-30b served by the oMLX evaluation backend. `config/backends.yaml` registers it in the `omlx-reasoning` entry (group `reasoning`, `priority: 10`), mapped from the `auto-data` workspace's `granite4.1:30b-ctx64k` model_hint. Added alongside `DeepSeek-R1-0528-Qwen3-8B-4bit` for the same reason as `Tongyi-DeepResearch-30B-A3B-abliterated-4bit` (see that unit) — `auto-data` pins its own model_hint distinct from `auto-reasoning`'s. Live-audited via a direct `/v1/chat/completions` tool-call probe (clean structured `tool_calls`, `finish_reason: tool_calls`, no template/tokenizer defects). Already on disk per `TASK_DAILY_WORK_FLEET_SOAK_V1`'s own per-category model table.

## Why

Grounds the model to the `omlx-reasoning` multi-model registration and the `auto-data` alias that lets its existing GGUF hint reach oMLX unchanged.
