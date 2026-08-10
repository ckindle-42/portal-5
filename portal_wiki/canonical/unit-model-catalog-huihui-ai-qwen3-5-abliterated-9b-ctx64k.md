---
id: unit-model-catalog-huihui-ai-qwen3-5-abliterated-9b-ctx64k
kind: what
title: "MODEL_CATALOG \u2014 `huihui_ai/qwen3.5-abliterated:9b-ctx64k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 956ee226e319e701e3605c9de6950bfa437a56f0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.653444
updated_at: 1784946220.653444
---

`huihui_ai/qwen3.5-abliterated:9b-ctx64k` is the 64K-context derived tag of the Qwen3.5-abliterated red-team model, registered in `config/backends.yaml` under both the `general` and `security` groups with `supports_tools: true`. `config/portal.yaml` routes the `auto-security` `purpleteam-deep` variant to this tag with a 65536 context limit, giving the four-hop purple chain the long window it needs for red, blue, detect, and IR hops. The `PARAMETER num_ctx 65536` is baked into the tag because Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`. Full model detail lives in the base `:9b` entry; this tag exists to give the deep purple chain its context headroom.

## Why

The `purpleteam-deep` routing in `config/portal.yaml` is the decisive binding — that four-hop chain is the only consumer of this specific tag — and `config/backends.yaml` confirms the dual-group `supports_tools: true`. The num_ctx mechanism is preserved because the long context window is the sole reason the derived tag was created, and it can only be expressed as a distinct model id.
