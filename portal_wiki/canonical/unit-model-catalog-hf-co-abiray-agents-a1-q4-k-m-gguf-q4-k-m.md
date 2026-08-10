---
id: unit-model-catalog-hf-co-abiray-agents-a1-q4-k-m-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M`"
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
created_at: 1784946220.610421
updated_at: 1784946220.610421
---

`hf.co/Abiray/Agents-A1-Q4_K_M-GGUF:Q4_K_M` is the Agents-A1 Q4_K_M (Apache 2.0, Qwen3.5-MoE 35B-A3B, 262K ctx, ~21GB, purpose-built long-horizon agentic). `config/backends.yaml` registers it in both the `general` and `coding` groups with `supports_tools: true` in each. `config/portal.yaml` selects it as the `model_hint` for `bench-agents-a1`, whose description records the self-reported τ2-Bench 79.8, IFEval 94.8, GAIA 96.0 figures and frames it as a direct competitor to AgentWorld and Ornith. It is V11 candidate intake (2026-06-30), bench-only with PROMOTE_POLICY=confirm, and was rehosted from InternScience to Abiray — the workspace label still says InternScience while the model id says Abiray.

## Why

The doc-derived body listed candidate details without pinning them to code. Re-grounding ties the id to `config/backends.yaml`, which proves the two groups and the `supports_tools: true` flags, and to `config/portal.yaml`, which proves the bench workspace, its self-reported numbers, and the promote policy. The rehost fact is visible in the config split between workspace label and model id, so the body states it as read from config rather than from a doc.
