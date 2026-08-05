---
id: unit-model-catalog-gemma4-12b-it-qat
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:12b-it-qat`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: db75e444cdca521f9be63059be9180bb380a4a64
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6387851
updated_at: 1784946220.6387851
---

`gemma4:12b-it-qat` is registered in `config/backends.yaml` under the `general` group with `supports_tools: false` and under the `vision` group with `supports_tools: true`. `config/portal.yaml` binds it as the `bench-gemma4-12b` workspace `model_hint` and names it in the `auto-audio` description as the first encoder-free audio model in the fleet (12B Unified QAT, ~7GB, 256K ctx, native function calling); the `auto-audio` workspace itself serves the derived `gemma4:12b-it-qat-ctx8k` tag. Released June 3, 2026; promoted to the `auto-audio` lane via its derived tag.

## Why

The vision-group registration asserts `supports_tools: true` while the general group keeps it false, and `config/portal.yaml` shows the base id is the `bench-gemma4-12b` `model_hint` while `auto-audio` uses the ctx8k derived tag. The encoder-free audio promotion is grounded in the `auto-audio` description, so the unit cites both config files rather than the prose catalog.
