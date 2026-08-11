---
id: unit-model-catalog-llama-3-2-3b-instruct-8bit
kind: what
title: "MODEL_CATALOG \u2014 `Llama-3.2-3B-Instruct-8bit`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: ed366c7a6eb34d822a5d4aa04f8072edca8acd5d
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1785716664.2314298
updated_at: 1785716664.2314298
---

`Llama-3.2-3B-Instruct-8bit` is the 8-bit MLX conversion of Llama-3.2-3B-Instruct (mlx-community), the cross-eval continuity model (2026-04-25 bake-off, 2026-05-28 re-eval, 2026-08-02 Phase-0). `config/backends.yaml` registers it in the `omlx` group's `omlx-local` backend with `supports_tools: false`. Phase-0 measured 62 t/s decode, 7.0x warm TTFT, and a JSON-schema PASS, but tool calling FAILS — bare JSON emitted in content, an oMLX Llama parser gap versus Ollama/llama.cpp — so Llama-family models are not migrated to oMLX tool paths until the parser handles them. It is not referenced by any `config/portal.yaml` workspace; it exists for eval continuity, not serving.

## Why

This unit grounds the MLX Llama model to the single `omlx-local` registration in backends.yaml, where the supports_tools false flag is the load-bearing fact, and records that no portal.yaml workspace consumes it. The Phase-0 measurements are kept as the institutional evidence behind the do-not-migrate note, which is a parser limitation rather than a model quality judgement.
