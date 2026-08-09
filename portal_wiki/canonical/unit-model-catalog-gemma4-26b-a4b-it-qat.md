---
id: unit-model-catalog-gemma4-26b-a4b-it-qat
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:26b-a4b-it-qat`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 63cbca4c591d2d00f1cc9e3101ffa91f84a9a4a0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.639137
updated_at: 1784946220.639137
---

`gemma4:26b-a4b-it-qat` is registered in `config/backends.yaml` under the `general` group with `supports_tools: true` and under the `vision` group with `supports_tools: true`. `config/portal.yaml` binds it as the `bench-gemma4-26b-qat` workspace `model_hint` and names it in the `auto-daily` description as the primary QAT model (26B-A4B MoE, ~15GB, 256K ctx, vision+text, QAT near-BF16), upgraded from the q4_K_M variant. It is bench-compared against the production q4_K_M primary; a separate promotion task swaps the primary if quality is confirmed better at similar TPS.

## Why

The `general` and `vision` group registrations in `config/backends.yaml` both assert `supports_tools: true`, and `config/portal.yaml` supplies the `bench-gemma4-26b-qat` binding and the `auto-daily` primary reference. The QAT-versus-q4_K_M comparison rationale is preserved as institutional knowledge because it explains why the model is registered as a bench candidate alongside the production primary.
