---
id: unit-model-catalog-hf-co-mia-ailab-qwable-3-6-35b-qwable-3-6-35b-q4-k-m-gguf-removed-from-security-group
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf`\
  \ \u2014 REMOVED from security group"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: a23f47b3e687df1693600eeea5b4f3f381b9da20
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.620333
updated_at: 1784946220.620333
---

This unit records the removal of Qwable-3.6-35B MoE from the security group and its substitution by `qwen3-coder:30b-a3b-q4_K_M`, the model_id this entry is anchored to. `config/backends.yaml` confirms the substitution target in the `coding` group with `supports_tools: true` and in the `general` group with `supports_tools: false`; Qwable itself (`hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf`) is present only in `coding` (true) and absent from `security` — mechanically proving the removal. `config/portal.yaml`'s `bench-qwable-35b` records the retirement (0.64 security-chain coverage below the 2/2 WIN threshold) and the fleet `ollama rm`. `qwen3-coder:30b-a3b-q4_K_M` is additionally the `model_hint` for `auto-coding`, `auto-security`, `auto-bigfix`, and `auto-cad`.

## Why

The doc claimed the config had drifted from the documented removal decision; re-grounding verifies the current state directly — `config/backends.yaml` places Qwable in `coding` only, never `security`, and lists the substitute `qwen3-coder:30b-a3b-q4_K_M` with its own flags. `config/portal.yaml` corroborates the retirement through `bench-qwable-35b`. The substitute-anchored model_id comes from the mapping; the body now states exactly what the two config files declare about both models.
