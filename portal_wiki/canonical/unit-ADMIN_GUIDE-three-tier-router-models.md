---
id: unit-ADMIN_GUIDE-three-tier-router-models
kind: why
title: "ADMIN_GUIDE \u2014 Three-Tier Router Models"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: Three-Tier Router Models
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.815375
updated_at: 1783195000.815375
---


Three models are available; select via `LLM_ROUTER_MODEL` in `.env`:

| Tier | Model | Accuracy | p50 Latency | VRAM | When to use |
|------|-------|----------|-------------|------|-------------|
| **PRIMARY** | `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M` | 82.2% | ~840ms | 5.3GB | Default — best accuracy |
| **STANDBY** | `llama3.2:3b` | 75.3% | ~433ms | ~2GB | If PRIMARY is evicted frequently in your fleet |
| **FALLBACK** | `qwen2.5:1.5b` | 67.1% | ~339ms | 1GB | Extremely memory-constrained; stays hot under any fleet load |

Accuracy figures are from `tests/benchmarks/bench_router.py` (36-query GOLDEN_SET, 3 rounds).
