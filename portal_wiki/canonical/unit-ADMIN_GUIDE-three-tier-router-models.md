---
id: unit-ADMIN_GUIDE-three-tier-router-models
kind: why
title: "ADMIN_GUIDE \u2014 Three-Tier Router Models"
sources:
- type: code
  path: .env.example
- type: code
  path: portal/platform/inference/router/routing.py
- type: code
  path: tests/benchmarks/bench_router.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.815375
updated_at: 1783195000.815375
---

Three router tiers are documented in `.env.example` and the header of routing.py. PRIMARY is `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M` — 82.2% accuracy, about 840ms warm latency, roughly 5.3GB, and the default `LLM_ROUTER_MODEL`. STANDBY is `llama3.2:3b` (75.3%, about 433ms, roughly 2GB). FALLBACK is `qwen2.5:1.5b` (67.1%, about 339ms, roughly 1GB). Switch tiers by setting `LLM_ROUTER_MODEL` and dropping `LLM_ROUTER_TIMEOUT_MS` to 500 for standby/fallback. The accuracy figures trace to `tests/benchmarks/bench_router.py`'s `GOLDEN_SET`.

## Why

Three tiers exist because accuracy and latency trade against each other on shared unified memory: the primary maximizes routing quality, the fallback's tiny footprint stays resident alongside inference models, and the standby splits the difference. The timeout must track the tier's warm latency, or every request falls through to Layer 2 keyword scoring.
