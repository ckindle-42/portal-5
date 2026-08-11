---
id: unit-model-catalog-qwen3-vl-32b
kind: what
title: "MODEL_CATALOG \u2014 `qwen3-vl:32b`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: ed366c7a6eb34d822a5d4aa04f8072edca8acd5d
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6369338
updated_at: 1784946220.6369338
---

`qwen3-vl:32b` is the production vision model, registered in `config/backends.yaml` under `group: vision` (`ollama-vision`) with `supports_tools: true`. The same group carries its `qwen3-vl:32b-ctx8k` derived tag, also marked `supports_tools: true`. `config/portal.yaml` routes the `auto-vision` workspace (module `general`) through the derived tag — `model_hint: qwen3-vl:32b-ctx8k` with `context_limit: 8192` — for image understanding, visual analysis, and multimodal tasks, and attaches the vision tools to that lane. The family's tool-calling flag is what lets the vision lane act on observations rather than merely describe them. The GGUF family is the production primary for this lane; a separate oMLX-held MLX conversion is an evaluation-only candidate.

## Why

Earlier this unit stated only that the family carries a tools tag, with no provenance for the claim. The vision-group `supports_tools: true` flag and the `auto-vision` workspace's `model_hint` are the two places this model's role is actually declared, so both are cited. The base-versus-derived distinction matters too: production routes on the capped tag while the base tag anchors the family.
