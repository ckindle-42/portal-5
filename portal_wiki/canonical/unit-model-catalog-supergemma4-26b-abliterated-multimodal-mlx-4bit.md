---
id: unit-model-catalog-supergemma4-26b-abliterated-multimodal-mlx-4bit
kind: what
title: "MODEL_CATALOG \u2014 `supergemma4-26b-abliterated-multimodal-mlx-4bit`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 86e6f142c0069ca2d4824b4721a545e64bd585b3
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1785716664.2314298
updated_at: 1785716664.2314298
---

`supergemma4-26b-abliterated-multimodal-mlx-4bit` is a VLM-shaped 4-bit MLX conversion of the abliterated supergemma4-26b fine-tune, registered in `config/backends.yaml` under `group: omlx` (`omlx-local`) with `supports_tools: true`. The group's live-probe notes attribute the tool_call PASS to the VLM engine because the fine-tune crashes text-only `mlx_lm`; oMLX's VLM engine is the only serving path. Phase-0 Gate-6 confirmed coherent generation plus structured `tool_calls`. It is an evaluation candidate for the auto-security redteam and purpleteam variants, which remain on the GGUF `supergemma4-26b-uncensored:Q4_K_M` family for production.

## Why

This model's `supports_tools: true` is meaningful only together with the serving-path constraint: native tool calling works exclusively through the VLM engine because text-only `mlx_lm` crashes on the fine-tune. Grounding the flag to the `omlx-local` entry and the engine requirement prevents the model from being mis-assumed safe to serve elsewhere, and marks its role as evaluation candidate rather than production.
