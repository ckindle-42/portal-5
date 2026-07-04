---
id: unit-ADMIN_GUIDE-ollama-max-loaded-models-3
kind: why
title: "ADMIN_GUIDE \u2014 OLLAMA_MAX_LOADED_MODELS=3"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: OLLAMA_MAX_LOADED_MODELS=3
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.815617
updated_at: 1783195000.815617
---


The Ollama slot count is set to **3** (not 2) for two reasons:

**1. Router keep-warm.** The router model holds its own slot alongside two inference models. Without this, Ollama evicts the router to make room for inference models — the first request after eviction falls back to Layer 2 keyword scoring while the router cold-loads.

**Cold-load times** (after eviction): PRIMARY 4.2s · STANDBY 2.4s · FALLBACK 1.6s. All exceed the production `LLM_ROUTER_TIMEOUT_MS` limit, so the first post-eviction request always goes to Layer 2 — exactly one fallback, then the router reloads and stays warm.

**2. Security multi-chain operations.** The purple team and security exec-chain workspaces (`auto-purpleteam`, `auto-purpleteam-deep`, `auto-purpleteam-exec`) run multi-hop model chains where two inference models need to be simultaneously warm: the attack model and the defender/blue-team model. The bench exec-chain driver (`tests/benchmarks/bench_security/cli.py`) explicitly relies on `MAX_LOADED=3` to pre-warm all chain models before any chain prompt runs — it evicts non-chain inference models first, then fills all 3 slots with chain models so no mid-chain eviction occurs.

In production, the purple team chain steps execute sequentially (not concurrently), but having both models loaded avoids a cold-load stall between hops. With `MAX_LOADED=2`, the second chain model evicts the first, causing a cold-load on every hop reversal.

**Bench parallelism (added 2026-06-29).** The default `MAX_LOADED` has been raised to **5**
to support `tests/benchmarks/bench_security.py --parallel-workspaces N` (default N=2).
The 4-hop `auto-purpleteam-deep` chain needs 4 distinct chain models hot; without `MAX_LOADED>=4`
Ollama evicts and re-cold-loads between hops, defeating the parallelism gain. Operators running
the security bench in parallel should verify the live Ollama process picks up the new value
(`ps eww -p $(pgrep -f "ollama serve") | tr ' ' '\n' | grep OLLAMA_MAX_LOADED`).
