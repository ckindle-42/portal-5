---
id: unit-model-catalog-hf-co-liquidai-lfm2-5-350m-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: fb9979b75eb4d70f331e849b80fc7326e8e61847
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.604196
updated_at: 1784946220.604196
---

`hf.co/LiquidAI/LFM2.5-350M-GGUF:Q4_K_M` is Liquid AI's LFM2.5-350M Q4_K_M (~230MB Q4, 128K ctx), an ultra-small variant in the LLM router classifier candidate set. `config/backends.yaml` registers it in the `general` group with `supports_tools: false`. `config/portal.yaml` selects it as the `model_hint` for `bench-lfm-micro-350m`, whose description records the CPU decode throughput and frames it as a router and daily-summarizer candidate, bench-only, evaluated via bench_router.py Round 4. Its role in the fleet is classification, not chat or tool dispatch, which is exactly what the false tool flag encodes.

## Why

The doc-derived "router classifier candidate" claim is now pinned: `config/portal.yaml`'s `bench-lfm-micro-350m` description states the router/daily-summarizer evaluation plan and the bench-only status, and `config/backends.yaml` supplies the `general`-group registration with `supports_tools: false`. The size/context figures are card metadata kept alongside the config-anchored role, so the unit reads as one step removed from doc prose and grounded in the two config files.
