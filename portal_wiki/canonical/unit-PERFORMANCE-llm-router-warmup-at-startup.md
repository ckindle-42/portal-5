---
id: unit-PERFORMANCE-llm-router-warmup-at-startup
kind: why
title: "PERFORMANCE \u2014 LLM Router Warmup at Startup"
sources:
- type: design
  path: docs/PERFORMANCE.md
  section: LLM Router Warmup at Startup
last_generated_commit: ''
confidence: high
tags:
- docs
- PERFORMANCE
created_at: 1783195000.8801239
updated_at: 1783195000.8801239
---

`_warmup_llm_router()` in `router_pipe.py` fires at pipeline startup to pre-load the intent classifier into Ollama VRAM before the first request arrives. The warmup uses `keep_alive: -1` (integer) — Ollama 0.30.8+ rejects the string form `"-1"`.
