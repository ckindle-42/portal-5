---
id: unit-model-catalog-gemma4-31b-it-qat
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:31b-it-qat`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 50b73876729db7181402fcbcc48400caa1ba1e40
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6394749
updated_at: 1784946220.6394749
---

`gemma4:31b-it-qat` is registered in `config/backends.yaml` under the `vision` group with `supports_tools: true` and under the `general` group with `supports_tools: false` (bench-only intake). `config/portal.yaml` binds it as the `bench-gemma4-31b-qat` workspace `model_hint`, describing a 31B Dense QAT (~18GB, 256K ctx, vision+text, QAT near-BF16). A 2026-06-21 bench scored quality 1.00 versus the q4_K_M variant's 0.00, and the q4_K_M entry was removed from the `general` group.

## Why

The `vision` group registration in `config/backends.yaml` asserts `supports_tools: true` (the general group keeps it false for bench-only intake), and `config/portal.yaml` supplies the `bench-gemma4-31b-qat` binding. The quality comparison and the q4_K_M removal are institutional notes explaining why the QAT variant is the registered one.
