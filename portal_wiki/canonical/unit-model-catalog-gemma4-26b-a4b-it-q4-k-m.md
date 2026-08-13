---
id: unit-model-catalog-gemma4-26b-a4b-it-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:26b-a4b-it-q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: f5987f1ea6b0cdb25b66e33a02b95183205d0605
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.637269
updated_at: 1784946220.637269
---

`gemma4:26b-a4b-it-q4_K_M` is registered in `config/backends.yaml` under the `general` group with `supports_tools: true` and under the `vision` group with `supports_tools: true`. `config/portal.yaml` binds it as the `bench-gemma4-26b-optiq` workspace `model_hint` and names it in the `auto-daily` description as the q4_K_M primary that was upgraded to the QAT variant. It is the Gemma 4 26B VLM Q4, the vision-capable model the general group also serves.

## Why

Both the `general` and `vision` group registrations in `config/backends.yaml` assert `supports_tools: true`, and `config/portal.yaml` supplies the `bench-gemma4-26b-optiq` binding plus the `auto-daily` upgrade note. The unit is grounded to both files because the model's reachability and its role as the pre-QAT vision primary are defined by the workspace entries, not the catalog.
