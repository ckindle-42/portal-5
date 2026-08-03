---
id: unit-model-catalog-llama-3-2-3b-instruct-8bit
kind: what
title: "MODEL_CATALOG — `Llama-3.2-3B-Instruct-8bit`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 29bdbca4
  section: '`Llama-3.2-3B-Instruct-8bit`'
last_generated_commit: 29bdbca4
confidence: high
tags:
- docs
created_at: 1785716664.2314298
updated_at: 1785716664.2314298
---

MLX conversion (mlx-community, 8-bit) of Llama-3.2-3B-Instruct, the cross-eval continuity model (2026-04-25 bake-off, 2026-05-28 re-eval, 2026-08-02 Phase-0). Phase-0: 62 t/s decode, 7.0x warm TTFT, JSON-schema PASS; tool calling FAILS (bare JSON in content, oMLX's Llama parser gap vs Ollama/llama.cpp) — do not migrate Llama-family models until this parses.
