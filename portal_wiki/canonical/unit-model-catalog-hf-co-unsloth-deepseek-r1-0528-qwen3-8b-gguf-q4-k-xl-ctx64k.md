---
id: unit-model-catalog-hf-co-unsloth-deepseek-r1-0528-qwen3-8b-gguf-q4-k-xl-ctx64k
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 86e6f142c0069ca2d4824b4721a545e64bd585b3
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.650228
updated_at: 1784946220.650228
---

`hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF:Q4_K_XL-ctx64k` is the 64K-context derived tag that `auto-reasoning` actually routes to: `config/portal.yaml` carries it as that workspace's `model_hint` and as the Operator and User Advocate role in the `auto-council` chain, and it appears in several persona `model_pin` / preferred lists. `config/backends.yaml` registers it under the `reasoning` group with `supports_tools: false`, matching the base tag. The `PARAMETER num_ctx 65536` is baked into the derived tag because Ollama's chat completions ignore request-time `options.num_ctx`, so a per-workspace context cap has to be a distinct model id. Full model detail lives in the base tag's entry.

## Why

The grounding here is routing: `config/portal.yaml` proves the `-ctx64k` tag, not the base id, is what `auto-reasoning`, `auto-council`, and multiple personas reference, while `config/backends.yaml` fixes the `reasoning` group and `supports_tools: false`. The num_ctx mechanism is preserved because it explains why a derived tag exists at all — a context limit that cannot be passed at request time must be encoded in the model id.
