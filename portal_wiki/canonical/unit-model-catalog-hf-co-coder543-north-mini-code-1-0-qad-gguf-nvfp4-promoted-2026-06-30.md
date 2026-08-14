---
id: unit-model-catalog-hf-co-coder543-north-mini-code-1-0-qad-gguf-nvfp4-promoted-2026-06-30
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF:NVFP4` \u2014\
  \ PROMOTED 2026-06-30"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 41df61e0a6102275a700700e9765972f1508c4c5
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.616704
updated_at: 1784946220.616704
---

`hf.co/coder543/North-Mini-Code-1.0-QAD-GGUF:NVFP4` is North-Mini-Code-1.0-QAD NVFP4 W4A16 (~19.3GB, Cohere Labs, Apache 2.0, cohere2moe arch, 256K ctx, 64K out, 30B-A3B MoE 128 experts top-8), an agentic-coding RL model. NVFP4 is weight-only quantization (activations stay BF16, no FP4 hardware required), and QAD claims >99% accuracy recovery vs unquantized. `config/backends.yaml` lists the base tag in the `general` group with `supports_tools: false`; the `coding` group's comment records the cohere_command4 tool-support attribution. `config/portal.yaml` selects the `-ctx8k` derived tag as the `model_hint` for the `northmini` variant of `auto-coding`, while the base id is the `model_hint` for `bench-north-mini-code`. The promotion to the `northmini` coding variant does not replace `auto-coding` (Qwen3-Coder-30B stays primary).

## Why

The doc body said the model was "PROMOTED 2026-06-30 to new auto-coding-northmini workspace"; re-grounding shows the promotion lands as the `northmini` VARIANT of the existing `auto-coding` workspace in `config/portal.yaml`, with the `-ctx8k` tag as its `model_hint`. `config/backends.yaml` supplies the group membership and the split `supports_tools` values. The cohere2moe smoke-load and non-replacement details are kept because the variant description and backends comments record them.
