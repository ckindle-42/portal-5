---
id: unit-known-limitations-devstral-24b-runtime-vram-footprint-25-7-gb
kind: what
title: "KNOWN_LIMITATIONS \u2014 devstral:24b Runtime VRAM Footprint (25.7 GB)"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: devstral:24b Runtime VRAM Footprint (25.7 GB)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6722538
updated_at: 1784946220.6722538
---

- **ID**: P5-VRAM-DEVSTRAL-001
- **Description**: devstral:24b file size is 14.3 GB but runtime Ollama resident size is ~25.7 GB due to large default context window and KV cache allocation (q8_0). This is nearly 2× the file size and can cause memory-pressure eviction of other loaded models; on M4 Pro 64 GB hardware this is non-critical (graceful CPU offload), but relevant on tighter budgets.
- **Impact**: When devstral is active, it may evict the LLM router model from VRAM. The first post-eviction routing request falls back to Layer 2 keyword scoring (correct behavior), then the router cold-loads in ~4.2s and stays warm. Subsequent requests use the LLM router normally.
- **This is graceful, not a crash**: Ollama offloads CPU layers under memory pressure rather than failing. Unlike the former MLX Metal OOM, no kernel panic occurs.
- **Mitigation**: `OLLAMA_MAX_LOADED_MODELS=3` (current default) reserves a slot for the router + 2 inference models. If devstral:24b is loading as an inference peer, its runtime footprint is the limiting factor — not the slot count. Setting `OLLAMA_MEMORY_LIMIT=42g` in the Ollama plist caps worst-case pressure; see Admin Guide → Router Configuration.
