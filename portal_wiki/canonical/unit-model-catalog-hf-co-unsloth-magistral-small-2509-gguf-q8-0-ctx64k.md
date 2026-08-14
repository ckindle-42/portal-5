---
id: unit-model-catalog-hf-co-unsloth-magistral-small-2509-gguf-q8-0-ctx64k
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: aae69a16de501e8524f279c9bff13f3fdc241f32
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.651062
updated_at: 1784946220.651062
---

`hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0-ctx64k` is the 64K-context derived tag of the Magistral-Small-2509 general-pool entry, registered in `config/backends.yaml` under the `general` group with `supports_tools: false`, inheriting the base tag's verdict. The `PARAMETER num_ctx 65536` is baked into the tag because Ollama's chat completions ignore request-time `options.num_ctx`, so the context cap must be a distinct model id. It has no `config/portal.yaml` workspace binding, so this entry exists solely to satisfy backend registry parity and to give a long-context variant of a reasoning-capable model a pullable id. Full model detail lives in the base tag's entry.

## Why

The `general`-group placement and `supports_tools: false` are determined by `config/backends.yaml`, and the absence of any `config/portal.yaml` binding is itself the fact to record. The num_ctx mechanism is preserved because it explains why the derived tag was created at all — a context window that cannot be passed at request time has to be a separate model id.
