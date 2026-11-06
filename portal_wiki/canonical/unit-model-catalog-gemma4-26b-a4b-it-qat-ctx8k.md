---
id: unit-model-catalog-gemma4-26b-a4b-it-qat-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:26b-a4b-it-qat-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.644711
updated_at: 1784946220.644711
---

`gemma4:26b-a4b-it-qat-ctx8k` is the context-bounded version of `gemma4:26b-a4b-it-qat`, holding an 8192-token window. `config/backends.yaml` registers it under the `vision` group with `supports_tools: true`. It was the `auto-daily` `model_hint` until 2026-10-18 (superseded by the ctx16k tag, then by the text-only Nemotron ctx32k tag on 2026-11-06) and stays registered as a fallback id. The limit is applied via `portal models apply-params` because the chat-completions API does not honor request-time context parameters, making a derived id necessary.

## Why

The `vision` group entry in `config/backends.yaml` carries the `supports_tools: true` value; this tag served `auto-daily` until 2026-10-18 and remains a registered fallback id. The two files jointly establish the registration and the consuming-workspace history, which is the grounding this unit needs.
