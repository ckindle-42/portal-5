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

`gemma4:26b-a4b-it-q4_K_M` is registered in `config/backends.yaml` under the `general` group with `supports_tools: true` and under the `vision` group with `supports_tools: true`. `config/portal.yaml` no longer binds it: the `bench-gemma4-26b-optiq` seat moved to `gemma4:26b-a4b-it-qat-ctx32k` (2026-11-06 QAT A/B, QAT 36/40 vs plain 32/40) and the `compliance-reading-overflow` 64k seat moved to `gemma4:26b-a4b-it-qat-ctx64k` the same day; the six vision personas still list it in their fallback lists pending the vision A/B. It is the Gemma 4 26B VLM Q4, the vision-capable model the general group also serves.

## Why

Both the `general` and `vision` group registrations in `config/backends.yaml` assert `supports_tools: true`; the workspace bindings moved to the QAT tags on 2026-11-06 (bench and 64k overflow, retirement batch 1), leaving the six vision personas' fallback lists as the remaining config consumers. The unit is grounded to both files because the model's reachability and its role as the pre-QAT vision primary are defined by the workspace entries, not the catalog.
