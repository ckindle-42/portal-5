---
id: unit-model-catalog-hf-co-coder543-north-mini-code-1-0-qad-gguf-nvfp4-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF:NVFP4-ctx8k`"
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
created_at: 1784946220.648161
updated_at: 1784946220.648161
---

`hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF:NVFP4-ctx8k` is the 8K-context derived tag of North-Mini-Code-1.0-QAD, promoted 2026-06-30 to the `northmini` variant of `auto-coding` as an additional lineage-diversity option. `config/backends.yaml` registers it in the `coding` group with `supports_tools: true`; the inline comment attributes tool support to the cohere_command4 parser on the cohere2moe architecture, which smoke-loaded cleanly on this Ollama build. `config/portal.yaml` selects this exact tag as the `model_hint` for the `northmini` variant of `auto-coding` — the coding workspace that keeps the Qwen3-Coder-30B primary untouched. `PARAMETER num_ctx 8192` is baked in via `portal models apply-params` because Ollama ignores request-time context options. The base `NVFP4` tag remains `bench-north-mini-code`'s `model_hint`.

## Why

The old body was the generic ctx-cap template. Re-grounding pins the derived tag to `config/backends.yaml` (coding group, `supports_tools: true`, cohere2moe/cohere_command4 comments) and to `config/portal.yaml` (the `northmini` variant's `model_hint`), which is the tag's only production consumer. The promoted-status and smoke-load claims are preserved because the config comments and variant description record them, not from doc recollection.
