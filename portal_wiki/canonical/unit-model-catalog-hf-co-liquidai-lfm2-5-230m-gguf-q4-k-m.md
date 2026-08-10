---
id: unit-model-catalog-hf-co-liquidai-lfm2-5-230m-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: de01e9b1e91aa629f9d80d26a890483a552e43e0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6046212
updated_at: 1784946220.6046212
---

`hf.co/LiquidAI/LFM2.5-230M-GGUF:Q4_K_M` is Liquid AI's LFM2.5-230M Q4_K_M (~150MB Q4, Apache 2.0, hybrid LIV conv + GQA), the smallest practical LFM2.5, a pipeline-internal workspace classifier candidate probing the router quality floor at minimal latency. `config/backends.yaml` registers it in the `general` group with `supports_tools: false`. `config/portal.yaml` selects it as the `model_hint` for `bench-lfm-micro-230m`, whose description explicitly states it is NOT a primary chat model — bench target only, evaluated via bench_router.py Round 4 for routing accuracy and security-refusal behavior. The `supports_tools: false` flag matches its classification-only role.

## Why

Re-grounding anchors this micro-model unit to the config that defines it: `config/backends.yaml` supplies the `general`-group registration and `supports_tools: false`, while `config/portal.yaml`'s `bench-lfm-micro-230m` description records the router-classifier role and the explicit "not a primary chat model" caveat. The doc's size and LIV/GQA detail are kept as card metadata, but the routing intent and flag are now config-verifiable.
