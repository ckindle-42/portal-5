---
id: unit-model-catalog-hf-co-unsloth-glm-4-7-flash-reap-23b-a3b-gguf-ud-q4-k-xl-ctx64k
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 50b73876729db7181402fcbcc48400caa1ba1e40
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.650646
updated_at: 1784946220.650646
---

`hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k` is the 64K-context derived tag that `config/portal.yaml` does not route as a workspace `model_hint`; instead it is consumed as a persona `model_pin` by the `glm-coder` persona in `config/personas/glm_coder.yaml`, which pins it onto the `auto-coding` workspace so the persona is served this exact tag. `config/backends.yaml` registers it under the `coding` group with `supports_tools: true`, the same group-level flag as its base tag. The `PARAMETER num_ctx 65536` is baked into the derived tag because Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`, making a context cap a per-tag property. See the base tag's entry for the full REAP detail.

## Why

This derived tag's grounding is the persona `model_pin`, not a workspace `model_hint` — the `glm-coder` persona pins the exact id, and `config/backends.yaml` fixes the `coding` group and `supports_tools: true`. Preserving the num_ctx mechanism is essential because it explains why the derived tag exists: the context window is encoded in the model id because the request-time option is ignored.
