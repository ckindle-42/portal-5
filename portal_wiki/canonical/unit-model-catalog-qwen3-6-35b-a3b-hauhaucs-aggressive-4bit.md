---
id: unit-model-catalog-qwen3-6-35b-a3b-hauhaucs-aggressive-4bit
kind: what
title: "MODEL_CATALOG \u2014 `Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 41df61e0a6102275a700700e9765972f1508c4c5
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786315000.0
updated_at: 1786315000.0
---

`Qwen3.6-35B-A3B-HauhauCS-Aggressive-4bit` is the 4-bit MLX conversion (dawncr0w's OptiQ build) of the Qwen3.6-35B-A3B HauhauCS-Aggressive-Uncensored fine-tune, served by the oMLX evaluation backend. `config/backends.yaml` registers it in the new `omlx-creative` entry (group `creative`, `priority: 10`, TASK_OMLX_FULL_PIPELINE_COVERAGE_V1) with `supports_tools: true`, live-audited via a direct `/v1/chat/completions` tool-call probe (clean structured `tool_calls`, `finish_reason: tool_calls`, no template/tokenizer defects found). The `aliases` block maps the production GGUF hint `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` onto this oMLX name, so the `auto-creative` daily workspace can now be served by oMLX with automatic Ollama fallback — no `config/portal.yaml` or `workspace_routing` change was needed.

## Why

Grounds the model to the `omlx-creative` registration that serves it and the alias that lets the existing GGUF hint reach oMLX unchanged. This is one of the four TASK_OMLX_FULL_PIPELINE_COVERAGE_V1 additions whose combined resident set (~63GB with the other three) exceeds oMLX's admission ceiling by design — the point of the parent task is to measure cross-group eviction/rejection under the full daily mix, not avoid it.
