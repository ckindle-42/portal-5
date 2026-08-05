---
id: unit-ADMIN_GUIDE-runtime-vram-vs-file-size-gap
kind: why
title: "ADMIN_GUIDE \u2014 Runtime VRAM vs File Size Gap"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: .env.example
- type: code
  path: portal/platform/inference/router/routing.py
- type: code
  path: portal/platform/inference/router/lifespan.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.8168268
updated_at: 1783195000.8168268
---

Ollama allocates the KV cache when a model loads, so a resident model's footprint is routinely larger than its GGUF file size; the gap grows with context length, KV quantization, and `OLLAMA_NUM_BATCH`. `devstral:24b` and `granite4.1:8b` are registered in `config/backends.yaml` (general group), and under large contexts a resident big model can push others — including the router — out of memory. Ollama offloads CPU layers rather than crashing; the evicted model cold-loads on its next request, so the first post-eviction `auto` request falls through to Layer 2 keyword scoring in routing.py. `OLLAMA_KEEP_ALIVE_REQUEST` (default `-1`) and `OLLAMA_MAX_LOADED_MODELS` bound residency, and lifespan.py's `_warmup_llm_router` re-pins the router after eviction.

## Why

File size is the wrong planning number because the KV cache is what actually competes for unified memory, making runtime residency diverge from size. Fleet and slot planning must budget resident footprint, and the graceful offload behavior is what makes an eviction a latency event rather than a crash.
