---
id: unit-model-catalog-vulnllm-r-7b-4bit
kind: what
title: "MODEL_CATALOG \u2014 `VulnLLM-R-7B-4bit`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 1ed83b22525c97ed996c835b7519e10c75d13ad0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786315000.0
updated_at: 1786315000.0
---

`VulnLLM-R-7B-4bit` is the 4-bit MLX conversion (mlx-community) of VulnLLM-R-7B (Qwen2-tokenizer based) served by the oMLX evaluation backend. `config/backends.yaml` registers it in the new `omlx-security` entry (group `security`, `priority: 10`, TASK_OMLX_FULL_PIPELINE_COVERAGE_V1) with `supports_tools: true`, live-audited via a direct `/v1/chat/completions` tool-call probe (clean structured `tool_calls`, `finish_reason: tool_calls`, no template/tokenizer defects found — unlike the reasoning-group model, this conversion's `tokenizer_class`/chat template worked correctly as shipped). The `aliases` block maps the production GGUF hint `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k` onto this oMLX name, so the `auto-security` daily workspace can now be served by oMLX with automatic Ollama fallback — no `config/portal.yaml` or `workspace_routing` change was needed.

## Why

Grounds the model to the `omlx-security` registration that serves it and the alias that lets the existing GGUF hint reach oMLX unchanged. Noting the clean audit result (no tokenizer/template defect, unlike the reasoning-group sibling model added in the same task) is useful context for a future session comparing why one of the four new backends needed deep root-causing and the others didn't.
