---
id: unit-model-catalog-hf-co-bartowski-qwen-qwen3-6-27b-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 9c0a4efa9fea8836ee3466b206c01b042c59455f
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.613865
updated_at: 1784946220.613865
---

`hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M` is the bartowski Q4_K_M of Qwen3.6-27B (~16GB). `config/backends.yaml` registers it in the `general` group with `supports_tools: false` and in the `coding` group with `supports_tools: true` — the tool-capable value applies only in the coding pool, per the Qwen3.6 tool-call format. `config/portal.yaml` selects it as the `model_hint` for `bench-qwen36-27b-optiq`, the TASK_QUANT_TRUEUP_V1 head-to-head lane: it was originally catalogued under an OptiQ label, but the bartowski repo was renamed to `Qwen_Qwen3.6-27B-GGUF` with no separate OptiQ GGUF published, so this quant stands in for the OptiQ comparison against `bench-qwen36-27b`.

## Why

The doc body asserted `supports_tools=true` flatly; re-grounding shows the flag is split in `config/backends.yaml` — `false` under `general`, `true` under `coding` — and fixes the claim to the config reality. `config/portal.yaml` pins the model to its bench workspace and preserves the OptiQ rename history that the bench description records. Every checkable assertion now traces to a config path.
