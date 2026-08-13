---
id: unit-model-catalog-huihui-ai-huihui-qwen3-5-9b-abliterated-mlx-4bit
kind: what
title: "MODEL_CATALOG \u2014 `huihui-ai--Huihui-Qwen3.5-9B-abliterated-mlx-4bit`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 75c5054f791636f367b62a1776bcc9f631794766
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786344000.0
updated_at: 1786344000.0
---

`huihui-ai--Huihui-Qwen3.5-9B-abliterated-mlx-4bit` is the 4-bit MLX conversion of huihui-ai's own Qwen3.5-9B-abliterated served by the oMLX evaluation backend. Registered in `omlx-security` (group `security`) as part of RBP arm coverage: the `auto-security` workspace folds 8 role variants (uncensored/pentest/blueteam/redteam/redteam-deep/purpleteam/purpleteam-deep/purpleteam-exec), each pinning a different `model_hint`, and `redteam`/`purpleteam`/`purpleteam-deep` all pin `huihui_ai/qwen3.5-abliterated:9b` (at ctx8k and ctx64k). This conversion was already resident in the hf-cache (unregistered until now) — no new pull required. Live tool-call-audited via a direct `/v1/chat/completions` probe (clean structured `tool_calls`, `finish_reason: tool_calls`) before being added with `supports_tools: true`.

## Why

Grounds the model to the `omlx-security` registration and the three role-variant aliases (`ctx8k` for redteam/purpleteam, `ctx64k` for purpleteam-deep) that map onto it. Notes the "already on disk, zero new disk cost" provenance because it's the reason this variant was added while the sibling `redteam-deep`/`purpleteam-exec` roles (supergemma4-26b) were deliberately left Ollama-backed — see `unit-module-security` for the fuller RBP-coverage decision record.
