---
id: unit-model-catalog-hf-co-liquidai-lfm2-5-1-2b-instruct-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.60373
updated_at: 1784946220.60373
---

`hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M` is Liquid AI's LFM2.5-1.2B-Instruct Q4_K_M (~780MB Q4, reasoning-capable, 32K ctx), the smallest LFM2.5 instruct variant, a candidate for the LLM router classifier role. `config/backends.yaml` registers it in the `general` group with `supports_tools: false` — a micro model intended for routing classification, not tool dispatch. `config/portal.yaml` selects it as the `model_hint` for `bench-lfm-micro-1p2b`, whose description frames it as a router + auto-extract / structured-output offload candidate, bench-only, with a bench_router.py Round 4 run and TPS probe called for. The `supports_tools: false` value aligns with that classification-only intent.

## Why

The doc body's "router classifier candidate" role is now grounded: `config/portal.yaml`'s `bench-lfm-micro-1p2b` description states the router/offload evaluation plan, and `config/backends.yaml` supplies the `general`-group registration and `supports_tools: false` flag. The size and context figures come from the doc card and the bench description. Every checkable claim traces to a config path rather than catalog prose.
