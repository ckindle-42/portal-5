---
id: unit-model-catalog-hf-co-unsloth-deepseek-r1-0528-qwen3-8b-gguf-q4-k-xl
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 1ed83b22525c97ed996c835b7519e10c75d13ad0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.635375
updated_at: 1784946220.635375
---

`hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL` is a ~5GB chain-of-thought distill of DeepSeek R1-0528 into an 8B Qwen3 base, registered in `config/backends.yaml` under the `reasoning` group with `supports_tools: false`. `config/portal.yaml` names it in the `auto-reasoning` workspace description as the model that replaced the Qwopus primary after pull failures, citing AIME 2024 parity with the much larger Qwen3-235B at a fraction of the size, while `deepseek-r1:32b` remains the reasoning-group fallback for heavy tasks. The base id carries no standalone bench workspace; the routed `model_hint` is the `-ctx64k` derived tag. The tool flag stays false because the chain-of-thought format is not tool-calling oriented.

## Why

The `reasoning`-group placement and `supports_tools: false` are asserted directly by `config/backends.yaml`, and `config/portal.yaml` supplies the production role in `auto-reasoning` plus the AIME parity rationale. The institutional knowledge that this is a smaller, faster reasoning tier complementing `deepseek-r1:32b` is preserved because the workspace description is exactly where that design intent is recorded.
