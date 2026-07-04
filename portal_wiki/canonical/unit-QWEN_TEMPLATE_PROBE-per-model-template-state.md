---
id: unit-QWEN_TEMPLATE_PROBE-per-model-template-state
kind: why
title: "QWEN_TEMPLATE_PROBE \u2014 Per-model template state"
sources:
- type: design
  path: docs/QWEN_TEMPLATE_PROBE.md
  section: Per-model template state
last_generated_commit: ''
confidence: high
tags:
- docs
- QWEN_TEMPLATE_PROBE
created_at: 1783195000.888695
updated_at: 1783195000.888695
---


Legend:
- **RED** — contains `|items` or `|safe` Python-only Jinja filters; will crash mlx_lm/mlx_vlm on tool calls. MUST be patched.
- **AMBER** — emits empty `<think></think>` blocks in history. Should be patched.
- **GREEN** — no known issues. Skip.
- **N/A** — model not present locally.

| Model | Family | Status | Findings | Source | Template file |
|---|---|---|---|---|---|
| `huihui-ai/Huihui-Qwen3.5-9B-abliterated-mlx-4bit` | qwen3.5 | **RED** | \|items | hf-cache | chat_template.jinja |
| `Jackrong/MLX-Qwopus3.5-27B-v3-8bit` | qwen3.5 | **GREEN** | clean | hf-cache | chat_template.jinja |
| `Jackrong/MLX-Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit` | qwen3.5 | **GREEN** | clean | hf-cache | chat_template.jinja |
| `mlx-community/Qwen3.6-27B-AEON-Ultimate-Uncensored-BF16-mlx-4Bit` | qwen3.6 | **RED** | \|items | hf-cache | chat_template.jinja |
| `mlx-community/Qwen3.6-35B-A3B-4bit` | qwen3.6 | **RED** | \|items | hf-cache | chat_template.jinja |
| `Jackrong/Negentropy-claude-opus-4.7-9B-6bit` | qwen3.5 | **RED** | \|items | hf-cache | chat_template.jinja |
| `froggeric/Qwen3.6-27B-MLX-4bit` | qwen3.6 | **GREEN** | clean | hf-cache | chat_template.jinja |
