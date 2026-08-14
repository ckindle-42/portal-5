---
id: unit-ADMIN_GUIDE-inference-health-monitoring
kind: why
title: "ADMIN_GUIDE \u2014 Inference Health Monitoring"
sources:
- type: code
  path: .env.example
- type: code
  path: scripts/lib/util.sh
- type: code
  path: scripts/lib/services.sh
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.81487
updated_at: 1783195000.81487
---

The inference tier is a single Ollama backend on port 11434, reached by the pipeline through `OLLAMA_URL` (default `http://host.docker.internal:11434`) and by the router through `LLM_ROUTER_OLLAMA_URL`. The MLX chat-inference proxy (ports 8081/18081/18082) was retired in commit 3a0c58e; its code remains only under `scripts/_archive/mlx-retired-3a0c58e/`. MLX survives strictly outside chat inference (speech, transcription, embeddings, reranking). Health monitoring is therefore `_cmd_status` in scripts/lib/util.sh: the `OLLAMA` row confirms the native server responds, and the pipeline block reports `backends_healthy` / `backends_total`.

## Why

With a single backend there is no proxy layer to supervise between the router and the models — health monitoring collapses to "is Ollama up and are the models resident." That simplification is exactly why the retired proxy's watchdog code was archived rather than maintained: supervision complexity scales with tier count, and the single-tier design removed the need for it.
