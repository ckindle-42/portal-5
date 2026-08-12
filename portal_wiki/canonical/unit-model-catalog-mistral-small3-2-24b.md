---
id: unit-model-catalog-mistral-small3-2-24b
kind: what
title: "MODEL_CATALOG \u2014 `mistral-small3.2:24b`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 10c7734f3f87df5a9d525bb5c1f3970c96a73a91
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6050088
updated_at: 1784946220.6050088
---

`mistral-small3.2:24b` is Mistral Small 3.2 (June 2025, Apache 2.0, 24B, ~14GB Q4) with improved function calling and instruction following over Small 3.1. `config/backends.yaml` registers it in `group: general` with `supports_tools: true`. `config/portal.yaml` uses it as a `council_models` entry in an auto-security blue variant and as the challenger member in `auto-council`'s member roster, so it reviews rather than serves a primary lane. It is the auto-mistral lane candidate and the `bench-mistral-small32` target per the catalog; the config tool flag matches the Mistral function-calling format.

## Why

Grounding ties the model to the general-group registration whose supports_tools true flag the config actually declares, and to the two portal.yaml placements (auto-security blue variant council and auto-council challenger) that consume it. The auto-mistral lane-candidate status is kept as catalog intent because no current workspace wires it as a `model_hint`.
