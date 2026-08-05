---
id: unit-model-catalog-gemma4-26b-a4b-it-qat-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:26b-a4b-it-qat-ctx8k`"
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
created_at: 1784946220.644711
updated_at: 1784946220.644711
---

`gemma4:26b-a4b-it-qat-ctx8k` is the context-bounded version of `gemma4:26b-a4b-it-qat`, holding an 8192-token window. `config/backends.yaml` registers it under the `vision` group with `supports_tools: true`. `config/portal.yaml` selects it as the `auto-daily` workspace `model_hint`, so the daily-driver lane reaches the QAT model through this capped tag. The limit is applied via `portal models apply-params` because the chat-completions API does not honor request-time context parameters, making a derived id necessary.

## Why

The `vision` group entry in `config/backends.yaml` carries the `supports_tools: true` value, and the `auto-daily` `model_hint` in `config/portal.yaml` is why the workspace resolves to this tag. The two files jointly establish the registration and the consuming workspace, which is the grounding this unit needs.
