---
id: unit-model-catalog-gemma4-e2b-it-qat
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:e2b-it-qat`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: aae69a16de501e8524f279c9bff13f3fdc241f32
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.63803
updated_at: 1784946220.63803
---

`gemma4:e2b-it-qat` is registered in `config/backends.yaml` under the `general` group with `supports_tools: false` and under the `vision` group with `supports_tools: true`. `config/portal.yaml` binds it as the `bench-gemma4-e2b` workspace `model_hint`, describing an effective 2B QAT (~3GB, 128K ctx, audio+image+video+text, thinking) that is the fastest TPS candidate in the fleet, with per-layer embeddings giving ~5.1B representational depth from 2.3B active parameters.

## Why

The `vision` group registration in `config/backends.yaml` asserts `supports_tools: true` while the `general` group keeps it false, and `config/portal.yaml` supplies the `bench-gemma4-e2b` binding plus the fleet-fastest TPS and PLE depth notes. The institutional performance claims are preserved because they justify the model's registered role as a bench candidate for the vision-capable QAT tier.
