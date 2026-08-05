---
id: unit-model-catalog-qwen3-coder-30b-a3b-instruct-4bit
kind: what
title: "MODEL_CATALOG \u2014 `Qwen3-Coder-30B-A3B-Instruct-4bit`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: fccb30525d4520443bca3fdbeebfbdb0fd6980f6
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1785716664.2314298
updated_at: 1785716664.2314298
---

`Qwen3-Coder-30B-A3B-Instruct-4bit` is the 4-bit MLX conversion of Qwen3-Coder-30B-A3B-Instruct (mlx-community) served by the oMLX evaluation backend. `config/backends.yaml` registers it in the `omlx` group's `omlx-local` backend and in `omlx-coding` (group `coding`), both with `supports_tools: true`; the `omlx-coding` `aliases` block maps the production GGUF hint `qwen3-coder:30b-a3b-q4_K_M-ctx16k` onto this oMLX name. Phase-0 probes measured decode 91.4 t/s versus 62.8 for the GGUF ctx16k tag, agentic-prefix warm TTFT 4.5x with verified cache hits, structured `tool_calls` PASS, and JSON-schema PASS. No `config/portal.yaml` workspace pins it directly.

## Why

Grounding anchors the model to the two omlx registrations that serve it and to the aliases block that lets the production GGUF hint reach oMLX unchanged. The Phase-0 probe numbers are kept as measured results, not config facts, and the unit notes the absence of any portal.yaml wiring so the eval-only role stays explicit.
