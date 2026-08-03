---
id: unit-model-catalog-qwen3-coder-30b-a3b-instruct-4bit
kind: what
title: "MODEL_CATALOG — `Qwen3-Coder-30B-A3B-Instruct-4bit`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 29bdbca4
  section: '`Qwen3-Coder-30B-A3B-Instruct-4bit`'
last_generated_commit: 29bdbca4
confidence: high
tags:
- docs
created_at: 1785716664.2314298
updated_at: 1785716664.2314298
---

MLX conversion (mlx-community, 4-bit) of Qwen3-Coder-30B-A3B-Instruct served by the oMLX evaluation backend (`omlx-local`, P5-FUT-013 Phase 1). Phase-0 probes: decode 91.4 t/s vs 62.8 for the production GGUF `-ctx16k` tag (1.46x), agentic-prefix warm TTFT 4.5x with verified cache hits, structured `tool_calls` PASS, JSON-schema PASS, 4-way concurrency 1.61x. See `tests/benchmarks/results/omlx_v3_reeval_20260802T221435Z.md`.
