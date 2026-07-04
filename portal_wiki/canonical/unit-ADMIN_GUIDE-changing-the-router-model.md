---
id: unit-ADMIN_GUIDE-changing-the-router-model
kind: why
title: "ADMIN_GUIDE \u2014 Changing the Router Model"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: Changing the Router Model
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.815854
updated_at: 1783195000.815854
---


All three variables live in `.env`:
```bash
LLM_ROUTER_MODEL=hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M
LLM_ROUTER_TIMEOUT_MS=1000   # 1000 for PRIMARY, 500 for STANDBY/FALLBACK
OLLAMA_MAX_LOADED_MODELS=5
```

Then restart the pipeline (not Ollama):
```bash
docker compose -f deploy/portal-5/docker-compose.yml restart portal-pipeline
```
