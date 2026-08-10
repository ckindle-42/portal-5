---
id: unit-known-limitations-devstral-24b-runtime-vram-footprint-25-7-gb
kind: what
title: "KNOWN_LIMITATIONS \u2014 devstral:24b Runtime VRAM Footprint (25.7 GB)"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
- type: code
  path: .env.example
last_generated_commit: fb9979b75eb4d70f331e849b80fc7326e8e61847
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6722538
updated_at: 1784946220.6722538
---

- **ID**: P5-VRAM-DEVSTRAL-001
- **Description**: `devstral:24b` is registered in `config/backends.yaml` under both the general and coding groups. `config/portal.yaml` lists its file size at ~14 GB, but runtime Ollama resident size runs roughly double that because a large default context window drives KV-cache allocation. This can cause memory-pressure eviction of other loaded models; on M4 Pro 64 GB it is non-critical (graceful CPU offload), but relevant on tighter budgets.
- **Impact**: When devstral is active, it may evict the LLM router model. The first post-eviction routing request falls back to Layer 2 keyword scoring (correct behavior), then the router cold-loads and stays warm; subsequent requests route normally.
- **This is graceful, not a crash**: Ollama offloads CPU layers under memory pressure rather than failing. Unlike the former MLX Metal OOM, no kernel panic occurs.
- **Mitigation**: `.env.example` sets `OLLAMA_MAX_LOADED_MODELS=5` (LLM router + 4 inference models), and `OLLAMA_MEMORY_LIMIT=0` (unlimited, native Ollama unaffected). If devstral:24b loads as an inference peer, its runtime footprint is the limiting factor — not the slot count. Worst-case slot composition stays within the 64 GB budget.

## Why

The catalog advertises devstral by its 14.3 GB file size, but the scheduler competes on resident footprint, so the ~25.7 GB runtime figure is the number that actually drives eviction decisions. Documenting the two numbers separately and describing the graceful CPU-offload behavior prevents a future operator from treating an eviction as a crash and "fixing" it with destructive measures.
