---
id: unit-model-catalog-hf-co-mia-ailab-qwable-3-6-35b-qwable-3-6-35b-q4-k-m-gguf
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf`"
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
created_at: 1784946220.614243
updated_at: 1784946220.614243
---

`hf.co/Mia-AiLab/Qwable-3.6-35b:Qwable-3.6-35b_q4_k_m.gguf` is Qwable-3.6-35B MoE Q4_K_M (~21GB, Mia-AiLab, MIT). `config/backends.yaml` registers it in the `coding` group only, with `supports_tools: true`; it is not present in the security group. `config/portal.yaml` selects it as the `model_hint` for `bench-qwable-35b`, whose description records the full arc: promoted to auto-pentest primary 2026-06-20, then RETIRED 2026-06-21 (SECURITY_FLEET_REVIEW_2026-06) when the fleet bench scored 0.64 coverage — below the CANDIDATE_EVAL_V1 2/2 WIN threshold — and the model was removed from the fleet via `ollama rm`. The bench workspace's current `model_hint` is `huihui_ai/baronllm-abliterated:latest`. The doc's older "PROMOTED to auto-pentest primary" claim is contradicted by the current config.

## Why

The doc body carried the stale promotion claim (29.7 t/s, 5/5 TPS, kerberoast_to_da 7/8) that `config/portal.yaml`'s `bench-qwable-35b` now records as reversed and retired. Re-grounding corrects the promotion claim, pins the `coding`-group registration and `supports_tools: true` in `config/backends.yaml`, and verifies the security-group absence and fleet removal from the config. The remaining knowledge — 3B-active MoE losing chain coherence — is preserved because the bench description states it.
