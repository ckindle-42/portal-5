---
id: unit-model-catalog-hf-co-bartowski-huihui-ai-qwen3-coder-next-abliterated-gguf-q4-k-m-ctx64k
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M-ctx64k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: d19bcd41d50c690918807eab095f1f738f9798d5
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.647757
updated_at: 1784946220.647757
---

`hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF:Q4_K_M-ctx64k` is the 64K-context derived tag of the abliterated Qwen3-Coder-Next. `config/backends.yaml` registers it in the `coding` group only, with `supports_tools: true` — the same value as its base tag in that group. `config/portal.yaml` uses it as the `model_hint` for `auto-spl` (Splunk/detection-authoring lane) and for the `uncensored-agentic` variant of `auto-coding`, both of which need the 64K window for long security-scripting or multi-turn agentic work. `PARAMETER num_ctx 65536` is baked in via `portal models apply-params` because Ollama ignores request-time `options.num_ctx`; a derived tag is what makes the wider context reachable. The base id itself carries no `model_hint` in production — only this capped variant does.

## Why

This unit previously parroted the generic derived-tag template from the doc. Re-grounding proves the tag's actual config footprint: `config/backends.yaml` supplies the `coding`-group registration and the `supports_tools: true` flag, and `config/portal.yaml` supplies the two workspaces (`auto-spl`, `auto-coding` uncensored-agentic) that select it as `model_hint`. The context-cap mechanism is stated because the config declares the derived tag, not from doc recollection.
