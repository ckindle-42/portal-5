---
id: unit-model-catalog-huihui-ai-qwen3-6-abliterated-27b-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `huihui_ai/Qwen3.6-abliterated:27b-ctx8k`"
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
created_at: 1784946220.651846
updated_at: 1784946220.651846
---

`huihui_ai/Qwen3.6-abliterated:27b-ctx8k` is the 8K-context derived tag of the Qwen3.6-abliterated 27B model, registered in `config/backends.yaml` under both the `general` and `creative` groups with `supports_tools: true`. `config/portal.yaml` routes the `auto-general-uncensored` workspace to this tag with an 8192 context limit, giving the uncensored generalist lane its promptable model. The `PARAMETER num_ctx 8192` is baked into the tag because Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`. Full model detail lives in the base `:27b` entry; this tag exists to enforce the general-uncensored lane's context cap as a distinct model id.

## Why

The `auto-general-uncensored` routing in `config/portal.yaml` is the decisive binding — that provisional uncensored generalist lane is the only consumer of this tag — and `config/backends.yaml` confirms the dual-group `supports_tools: true`. The num_ctx mechanism is preserved because it explains why the 8K variant exists apart from the base id and why the base id itself carries no direct production routing.
