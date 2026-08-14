---
id: unit-model-catalog-huihui-ai-qwen3-5-abliterated-9b-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `huihui_ai/qwen3.5-abliterated:9b-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 64c5f5f41652bf67e97863ee1a6285289eaeea00
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6539059
updated_at: 1784946220.6539059
---

`huihui_ai/qwen3.5-abliterated:9b-ctx8k` is the 8K-context derived tag of the Qwen3.5-abliterated red-team model, registered in `config/backends.yaml` under both the `general` and `security` groups with `supports_tools: true`. `config/portal.yaml` routes it through the `auto` router's `model_hint` and through the `auto-security` `redteam` and `purpleteam` variants, all at an 8192 context limit. The `PARAMETER num_ctx 8192` is baked into the tag because Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`. Full model detail lives in the base `:9b` entry; this tag exists to enforce the security lanes' context cap as a distinct model id.

## Why

The `config/portal.yaml` bindings — the `auto` router and both the `redteam` and `purpleteam` variants — are the facts that make this the most-referenced derived tag of the family, and `config/backends.yaml` confirms the dual-group `supports_tools: true`. The num_ctx mechanism is preserved because it explains why the 8K tag exists separately from the base and the 64K sibling: per-workspace context caps must be model ids.
