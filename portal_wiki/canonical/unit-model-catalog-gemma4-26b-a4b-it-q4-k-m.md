---
id: unit-model-catalog-gemma4-26b-a4b-it-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:26b-a4b-it-q4_K_M`"
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
created_at: 1784946220.637269
updated_at: 1784946220.637269
---

`gemma4:26b-a4b-it-q4_K_M` is registered in `config/backends.yaml` under the `general` group with `supports_tools: true` and under the `vision` group with `supports_tools: true`. `config/portal.yaml` binds it as the `bench-gemma4-26b-optiq` workspace `model_hint`; the `auto-daily` description named it the q4_K_M primary that was upgraded to the QAT variant, until the seat moved to the text-only Nemotron ctx32k tag (2026-11-06). It is the Gemma 4 26B VLM Q4, the vision-capable model the general group also serves.

## Why

Both the `general` and `vision` group registrations in `config/backends.yaml` assert `supports_tools: true`, and `config/portal.yaml` supplies the `bench-gemma4-26b-optiq` binding plus the `auto-daily` upgrade note (historical since the 2026-11-06 seat move). The unit is grounded to both files because the model's reachability and its role as the pre-QAT vision primary are defined by the workspace entries, not the catalog.
