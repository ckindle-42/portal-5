---
id: unit-model-catalog-gemma-4-e4b-it-4bit
kind: what
title: "MODEL_CATALOG — `gemma-4-e4b-it-4bit`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 29bdbca4
  section: '`gemma-4-e4b-it-4bit`'
last_generated_commit: 29bdbca4
confidence: high
tags:
- docs
created_at: 1785716664.2314298
updated_at: 1785716664.2314298
---

MLX conversion (mlx-community, 4-bit) of gemma-4-e4b-it served by the oMLX evaluation backend. Phase-0 probes: decode ~74 t/s vs ~49 for GGUF `gemma4:e4b-it-qat` (~1.4x), warm TTFT 3.5x, structured `tool_calls` PASS via Gemma `<start_function_call>` parsing, JSON-schema PASS with one reproducible livelock on unconstrained-to-constrained request transitions (self-recovering; filed upstream draft).
