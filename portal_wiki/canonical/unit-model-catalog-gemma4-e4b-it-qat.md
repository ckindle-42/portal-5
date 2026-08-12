---
id: unit-model-catalog-gemma4-e4b-it-qat
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:e4b-it-qat`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 640a004e4a83811639544dfada51fcd1268b0688
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.63837
updated_at: 1784946220.63837
---

`gemma4:e4b-it-qat` is registered in `config/backends.yaml` under the `general` group with `supports_tools: false` and under the `vision` group with `supports_tools: true`. `config/portal.yaml` binds it as the `bench-gemma4-e4b-qat` workspace `model_hint`, describing an effective 4B QAT (~5GB, 128K ctx, audio+image+video+text, thinking, QAT near-BF16 at 4-bit) positioned as a quality upgrade over the production `gemma4:e4b-it-q4_K_M`.

## Why

The `vision` group registration in `config/backends.yaml` asserts `supports_tools: true` while the `general` group keeps it false, and `config/portal.yaml` supplies the `bench-gemma4-e4b-qat` binding and the quality-upgrade framing. The unit is grounded to both files so the QAT-versus-q4 comparison is tied to the workspace entry that actually selects the model.
