---
id: unit-ADMIN_GUIDE-runtime-vram-vs-file-size-gap
kind: why
title: "ADMIN_GUIDE \u2014 Runtime VRAM vs File Size Gap"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: Runtime VRAM vs File Size Gap
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.8168268
updated_at: 1783195000.8168268
---


Ollama allocates KV cache at model-load time. Runtime resident size is **significantly larger** than the model file:

| Model | File size | Runtime VRAM | Driver |
|-------|-----------|--------------|--------|
| devstral:24b | 14.3 GB | ~25.7 GB | Large default context window |
| granite4.1:8b | 5.3 GB | ~16.8 GB | Large context + KV q8_0 |
| OBLITERATED E4B | 5.3 GB | ~5.3 GB | Compact architecture |

**devstral:24b specifically**: its 25.7 GB runtime footprint can cause memory-pressure eviction of other models regardless of `MAX_LOADED_MODELS`. This is expected graceful behavior — Ollama offloads CPU layers rather than crashing (unlike MLX Metal OOM). If devstral evicts the router, Layer 2 keyword scoring handles that one request, then the router reloads. Not a bug.
