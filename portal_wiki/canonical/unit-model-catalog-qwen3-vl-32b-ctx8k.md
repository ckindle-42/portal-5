---
id: unit-model-catalog-qwen3-vl-32b-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `qwen3-vl:32b-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: fccb30525d4520443bca3fdbeebfbdb0fd6980f6
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.658004
updated_at: 1784946220.658004
---

`qwen3-vl:32b-ctx8k` is the context-capped derivation of `qwen3-vl:32b` that bakes `PARAMETER num_ctx 8192` into the tag so the vision lane does not reserve a full native context window per request. `config/backends.yaml` lists it under `group: vision` (`ollama-vision`) with `supports_tools: true`, and `config/portal.yaml` wires it as the `model_hint` of the `auto-vision` workspace whose `context_limit` is `8192`. The tag exists because Ollama's `/v1/chat/completions` drops request-time `options.num_ctx`, so a per-workspace cap has to be a distinct model tag rather than a request option. The production vision workspace therefore always runs the capped tag, never the uncapped base.

## Why

This entry exists to record that the vision lane's context is controlled by the derived tag, not by request options, and to bind that fact to the two config files that make it true: the `vision` group entry and the `auto-vision` workspace pin. Without the tag, every vision request would reserve context far beyond the workspace's declared limit and evict other models from memory.
