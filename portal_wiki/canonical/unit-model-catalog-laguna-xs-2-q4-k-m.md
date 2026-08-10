---
id: unit-model-catalog-laguna-xs-2-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `laguna-xs.2:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 9c0a4efa9fea8836ee3466b206c01b042c59455f
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6080582
updated_at: 1784946220.6080582
---

`laguna-xs.2:Q4_K_M` is the Q4 GGUF registration of poolside/Laguna-XS.2, a 33B-A3B MoE (~19GB, 68.2% SWE-bench Verified). `config/backends.yaml` lists it in `group: general` with `supports_tools: false` and in `group: coding` with `supports_tools: true`, so the tool flag is resolved per backend group rather than globally. `config/portal.yaml` pins it as the `bench-laguna` workspace `model_hint`; that workspace's description records the 2026-06-20 promotion to the auto-coding-agentic primary and the 2/2 security chain at 63s. The opencode/Claude Code default resolves through this bench entry.

## Why

This unit re-sources the laguna promotion claim to the bench-laguna workspace description that actually records it, and to the two backend groups where the id appears, fixing the supports_tools value to its per-group truth instead of a single doc-only figure. The SWE-bench percentage is kept as the recorded benchmark attribute of the model, not as a config-derived number.
