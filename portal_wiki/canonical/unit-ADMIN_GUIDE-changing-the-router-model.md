---
id: unit-ADMIN_GUIDE-changing-the-router-model
kind: why
title: "ADMIN_GUIDE \u2014 Changing the Router Model"
sources:
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
created_at: 1783195000.815854
updated_at: 1783195000.815854
---

The router model is chosen through `.env`: `LLM_ROUTER_MODEL` (default `hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M`), `LLM_ROUTER_TIMEOUT_MS` (1000 for the primary, 500 for standby/fallback), plus `LLM_ROUTER_CONFIDENCE_THRESHOLD` and `LLM_ROUTER_ENABLED`. routing.py reads these into `_LLM_ROUTER_MODEL` and `_LLM_ROUTER_TIMEOUT_MS` at startup, and lifespan.py's `_warmup_llm_router` pre-loads the configured model with `keep_alive: -1`. Apply a change by editing `.env` and restarting only the pipeline container:

```bash
docker compose -f deploy/portal-5/docker-compose.yml restart portal-pipeline
```

Ollama needs no restart because the router model is an ordinary Ollama model.

## Why

The router is a classification model, not an inference tier, so swapping it is config plus a restart with no retraining and no backend rework. The model and its timeout are coupled — the timeout is tuned to the tier's warm latency, so changing one without the other silently pushes requests into Layer 2 fallback instead of giving the new model a chance.
