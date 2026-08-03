---
id: unit-model-catalog-supergemma4-26b-abliterated-multimodal-mlx-4bit
kind: what
title: "MODEL_CATALOG — `supergemma4-26b-abliterated-multimodal-mlx-4bit`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 29bdbca4
  section: '`supergemma4-26b-abliterated-multimodal-mlx-4bit`'
last_generated_commit: 29bdbca4
confidence: high
tags:
- docs
created_at: 1785716664.2314298
updated_at: 1785716664.2314298
---

VLM-shaped MLX conversion (Jiunsong, 4-bit) of the supergemma4-26b abliterated fine-tune, served by oMLX's VLM engine. P5-MLX-EVAL-005 recorded that every MLX conversion of this fine-tune crashes text-only `mlx_lm`; oMLX's VLMEngine serves it — Phase-0 Gate-6: coherent generation + structured `tool_calls` PASS. Migration candidate for auto-security redteam/purpleteam variants.
