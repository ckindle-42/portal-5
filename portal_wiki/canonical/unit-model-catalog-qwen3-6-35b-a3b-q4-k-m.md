---
id: unit-model-catalog-qwen3-6-35b-a3b-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `qwen3.6:35b-a3b-q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 86e6f142c0069ca2d4824b4721a545e64bd585b3
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.611625
updated_at: 1784946220.611625
---

`qwen3.6:35b-a3b-q4_K_M` is the Qwen3.6-35B-A3B MoE Q4 build (~22GB, Alibaba, April 2026, Apache 2.0, 262K ctx) with 3B active for fast decode at 35B-class quality. `config/backends.yaml` registers it in `group: general` with `supports_tools: false` and in `group: coding` with `supports_tools: true`. `config/portal.yaml` pins it as the `bench-qwen36-35b-a3b` workspace `model_hint`. Earlier auto-compliance promotion prose no longer matches portal.yaml, whose auto-compliance `model_hint` points at the Granite entry; the verifiable wiring today is the bench workspace.

## Why

Grounding anchors the model to its two backends.yaml registrations with their per-group supports_tools split, and to the bench workspace that pins it as `model_hint`. The old auto-compliance promotion is corrected because portal.yaml's auto-compliance `model_hint` value does not reference this id; the bench placement is the only production wiring the config supports.
