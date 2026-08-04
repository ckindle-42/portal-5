---
id: unit-model-catalog-hf-co-jackrong-qwopus3-6-27b-v2-mtp-gguf-qwopus3-6-27b-v2-mtp-q5-k-m-gguf
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: ba66a30a47f104a137e20da5d5a3e3e9cc0b3360
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.633884
updated_at: 1784946220.633884
---

`hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF:Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf` is Qwopus3.6-27B-v2 MTP Q5 (~19GB, Jackrong, Apache 2.0, June 2026, 27B dense, self-speculative MTP decoding). `config/backends.yaml` registers it in the `general` group with `supports_tools: false` and in the `reasoning` group with `supports_tools: true` — it is tool-capable in the reasoning pool where it was intended to serve. `config/portal.yaml` selects it as the `model_hint` for `bench-qwopus-coder-mtp-v2`, whose description records the v1 retirement (quality 0.67, 6.5 TPS) and the v2 probe result 10/23 with widespread 500 errors, PROMOTE_POLICY=blocked. The original `auto-reasoning` primary pull failed (hf.co repo not llama.cpp-compatible as of 2026-06-09), so auto-reasoning now falls back to reasoning-group models.

## Why

The doc body's "auto-reasoning primary" wording is corrected: `config/portal.yaml`'s `bench-qwopus-coder-mtp-v2` is the model's actual home (PROMOTE_POLICY=blocked), and the `auto-reasoning` workspace pins `DeepSeek-R1-0528-Qwen3-8B` instead, as its description records the Qwopus pull-failure fallback. `config/backends.yaml` supplies the group-split `supports_tools` flags. The bench numbers (10/23, v1 0.67/6.5 TPS) are retained because the bench workspace description carries them.
