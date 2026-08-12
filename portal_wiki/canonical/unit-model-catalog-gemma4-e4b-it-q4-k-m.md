---
id: unit-model-catalog-gemma4-e4b-it-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:e4b-it-q4_K_M`"
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
created_at: 1784946220.63768
updated_at: 1784946220.63768
---

`gemma4:e4b-it-q4_K_M` is registered in `config/backends.yaml` under the `general` group with `supports_tools: true` and under the `vision` group with `supports_tools: true`. `config/portal.yaml` binds it as the `bench-gemma4-e4b` workspace `model_hint`, describing it as a Google MoE with 4B active (~9.6GB, 128K ctx, vision+thinking+tools) and a daily-driver candidate. The catalog's corrected notes record audio+image+video input and thinking mode, with per-layer embeddings giving representational depth beyond the 4B weight count; an audit-tools run on 2026-06-18 confirmed tool_call. It is retained as the production vision fallback while the QAT variant is benchmarked.

## Why

Both the `general` and `vision` group registrations in `config/backends.yaml` assert `supports_tools: true`, matching the audit-tools confirmation, and `config/portal.yaml` supplies the `bench-gemma4-e4b` binding with the ~9.6GB size and daily-driver framing. The corrected input-mode and PLE notes are kept as institutional knowledge that explains the model's role as vision fallback.
