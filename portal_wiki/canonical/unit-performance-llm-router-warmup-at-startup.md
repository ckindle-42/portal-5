---
id: unit-performance-llm-router-warmup-at-startup
kind: what
title: "PERFORMANCE \u2014 LLM Router Warmup at Startup"
sources:
- type: doc
  path: docs/PERFORMANCE.md
  commit: 05e42ec2
  section: LLM Router Warmup at Startup
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.509268
updated_at: 1784946220.509268
---

`_warmup_llm_router()` in `router_pipe.py` fires at pipeline startup to pre-load the intent classifier into Ollama VRAM before the first request arrives. The warmup uses `keep_alive: -1` (integer) — Ollama 0.30.8+ rejects the string form `"-1"`.
