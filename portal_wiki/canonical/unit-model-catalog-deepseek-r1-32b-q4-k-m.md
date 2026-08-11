---
id: unit-model-catalog-deepseek-r1-32b-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `deepseek-r1:32b-q4_k_m`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: d19bcd41d50c690918807eab095f1f738f9798d5
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.630338
updated_at: 1784946220.630338
---

`deepseek-r1:32b-q4_k_m` is registered in `config/backends.yaml` under the `reasoning` backend group with `supports_tools: false`. In `config/portal.yaml` the `auto-reasoning` workspace description names it as the reasoning-group fallback for heavy tasks, and the GLM-Z1-Rumination bench workspace lists it as a candidate for the auto-reasoning pool alongside `glm-4.7-flash:Q4_K_M`. The model pull registry records its source (DeepSeek-R1-Distill-Qwen-32B) with a retired flag. The model is reasoning-trained and chain-of-thought oriented, not tool-trained; `supports_tools: false` is intentional to prevent reasoning-budget exhaustion from mixing with tool-call rendering.

## Why

The `reasoning` group placement and the `supports_tools: false` flag are asserted directly by `config/backends.yaml`, and `config/portal.yaml` confirms its fallback and candidate roles in workspace descriptions. The institutional claim that this is a reasoning-trained, not tool-trained model is preserved because the config flag is the mechanical expression of that design decision.
