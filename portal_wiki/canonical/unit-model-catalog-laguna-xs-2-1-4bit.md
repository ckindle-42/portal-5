---
id: unit-model-catalog-laguna-xs-2-1-4bit
kind: what
title: "MODEL_CATALOG \u2014 `Laguna-XS-2.1-4bit`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1790304303.634454
updated_at: 1790304303.634454
---

`Laguna-XS-2.1-4bit` is mlx-community's 4-bit MLX conversion of poolside/Laguna-XS-2.1 (33B total, 3B active, 262K context), served by oMLX. `config/backends.yaml` registers it in the no-traffic `omlx-local` holding entry (group `omlx`) and in the live `omlx-coding` entry (group `coding`, `priority: 10`), both with `supports_tools: true`. The `omlx-coding` `aliases` block maps `portal5/laguna-xs21:q4_K_M-ctx128k` (the auto-coding `laguna` variant's `model_hint`, derived from the Ollama library `laguna-xs-2.1`) onto this oMLX name, so oMLX serves the seat and Ollama is the fallback. It replaced Laguna-XS.2 on 2026-09-25.

## Why

XS.2 could not stop after a tool call on this stack: it chained invented calls to the token cap in one turn, on both our import and Ollama's official build, so every opencode turn could run to the limit. 2.1 stops correctly and scored 29/42 (coding 9/9) on the laguna-seat WFE via oMLX, against MiMo's 11/42 on the same instrument. It is served by oMLX rather than Ollama because Ollama 0.34.2's Laguna parser returns HTTP 500 ("empty Laguna tool call name") on any reply that begins with a bare JSON object; oMLX's parser does not.
