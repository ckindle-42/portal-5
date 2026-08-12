---
id: unit-model-catalog-gemma-4-26b-a4b-it-qat-4bit
kind: what
title: "MODEL_CATALOG \u2014 `gemma-4-26b-a4b-it-QAT-4bit`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 640a004e4a83811639544dfada51fcd1268b0688
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786315000.0
updated_at: 1786315000.0
---

`gemma-4-26b-a4b-it-QAT-4bit` is the 4-bit QAT MLX conversion of gemma-4-26b-a4b-it served by the oMLX evaluation backend. `config/backends.yaml` registers it in the new `omlx-general` entry (group `general`, `priority: 10`, TASK_OMLX_FULL_PIPELINE_COVERAGE_V1) with `supports_tools: true`, live-audited via a direct `/v1/chat/completions` tool-call probe (clean structured `tool_calls`, `finish_reason: tool_calls`). The `aliases` block maps the production GGUF hint `gemma4:26b-a4b-it-qat-ctx8k` onto this oMLX name, so `general`-group daily workspaces (`auto-daily` and the general fallback) can now be served by oMLX with automatic Ollama fallback — no `config/portal.yaml` or `workspace_routing` change was needed.

## Why

Grounds the model to the `omlx-general` registration that serves it and the alias that lets the existing GGUF hint reach oMLX unchanged. The measured (not assumed) `supports_tools: true` result is the load-bearing fact — the whole point of the Phase 1 audit in TASK_OMLX_FULL_PIPELINE_COVERAGE_V1 was to not flag a model as tool-capable without a live probe.
