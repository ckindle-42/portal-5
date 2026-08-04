---
id: unit-QWEN_TEMPLATE_PROBE-interpretation-for-task-qwen-template-proxy-v1
kind: why
title: "QWEN_TEMPLATE_PROBE \u2014 Interpretation for TASK_QWEN_TEMPLATE_PROXY_V1"
sources:
- type: design
  path: docs/QWEN_TEMPLATE_PROBE.md
  section: Interpretation for TASK_QWEN_TEMPLATE_PROXY_V1
last_generated_commit: ''
confidence: high
tags:
- docs
- QWEN_TEMPLATE_PROBE
created_at: 1783195000.888937
updated_at: 1783195000.888937
---


**Server flags**: `mlx_lm.server` accepts `--chat-template` (inline string, not a file path).
`mlx_vlm.server` has no runtime chat-template override flag.

Implement the proxy injection path in T8 using `--chat-template` with inline content for
mlx_lm models. mlx_vlm models (e.g. `mlx-community/Qwen3.6-35B-A3B-4bit` which is VLM)
rely on disk patching only.

**Models for TASK_QWEN_TEMPLATE_PROMOTE_V1** (RED rows only; GREEN rows are already clean):
- `huihui-ai/Huihui-Qwen3.5-9B-abliterated-mlx-4bit` → patch qwen3.5
- `mlx-community/Qwen3.6-27B-AEON-Ultimate-Uncensored-BF16-mlx-4Bit` → patch qwen3.6
- `mlx-community/Qwen3.6-35B-A3B-4bit` → patch qwen3.6 (VLM — disk only, no proxy injection)
- `Jackrong/Negentropy-claude-opus-4.7-9B-6bit` → patch qwen3.5

**SKIP**: Qwopus 27B v3, Qwopus v2 (both already GREEN), and froggeric (GREEN by design).
This changes the promote task scope from 6 models to 4 models.
