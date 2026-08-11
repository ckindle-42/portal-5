---
id: unit-model-catalog-gemma-4-e4b-it-4bit
kind: what
title: "MODEL_CATALOG \u2014 `gemma-4-e4b-it-4bit`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 1896bb7da29dd96ff280b8ffb495519d507070ee
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1785716664.2314298
updated_at: 1785716664.2314298
---

`gemma-4-e4b-it-4bit` is registered in `config/backends.yaml` under the `omlx` group with `supports_tools: true`, served by the oMLX evaluation backend (`type: omlx`). It is the MLX conversion (mlx-community, 4-bit) of gemma-4-e4b-it. Phase-0 probes measured roughly 74 t/s decode versus about 49 t/s for the GGUF `gemma4:e4b-it-qat` (~1.4x), a 3.5x warmer TTFT, and a structured `tool_calls` PASS via Gemma `<start_function_call>` parsing, with JSON-schema PASS and one reproducible self-recovering livelock on unconstrained-to-constrained transitions.

## Why

The `omlx` group registration in `config/backends.yaml` is the model's only config grounding — it is a holding group with no workspace routing reference, so the backend entry carries the id, the tool flag, and the oMLX type. The probe numbers are institutional knowledge from the oMLX evaluation phase and are kept because they justify the `supports_tools: true` decision recorded in the entry.
