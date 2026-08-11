---
id: unit-model-catalog-hf-co-deepreinforce-ai-ornith-1-0-35b-gguf-q4-k-m-promoted-2026-06-30
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M` \u2014\
  \ PROMOTED 2026-06-30"
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
created_at: 1784946220.6162739
updated_at: 1784946220.6162739
---

`hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF:Q4_K_M` is Ornith-1.0-35B Q4_K_M (~21GB, DeepReinforce/MIT, Qwen3.5-35B-A3B base, 262K ctx, MoE 3B active), sharing its self-improving RL training with the 9B sibling. It was a V10 candidate under `bench-ornith-35b`, substituting for the operator-requested AEON-7 NVFP4 (Blackwell-only). `config/backends.yaml` registers it in the `general` group with `supports_tools: false` and in the `coding` group with `supports_tools: true`. `config/portal.yaml` promoted it 2026-06-30 to the `ornith` variant of `auto-coding` (whose `model_hint` is the `-ctx64k` derived tag) on strong tool-chain 4/5 and SWE-handoff 4/5 probe markers; the variant sits alongside `auto-coding`'s heavy and lite variants without replacing either. The base id remains `bench-ornith-35b`'s `model_hint`.

## Why

The doc body claimed promotion to a standalone "auto-agentic-ornith workspace"; `config/portal.yaml` shows the real target is the `ornith` variant of the existing `auto-coding` workspace, and `config/backends.yaml` supplies the per-group `supports_tools` values. Re-grounding corrects the workspace naming to match config, keeps the AEON-7 substitution rationale from the bench description, and preserves the tool-chain/SWE-handoff probe markers recorded in the variant description.
