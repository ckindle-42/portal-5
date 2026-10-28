---
id: unit-readme-core-models-pulled-automatically-on-first-run-4-gb
kind: what
title: "README \u2014 Core models (pulled automatically on first run, ~4 GB)"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: .env.example
- type: code
  path: portal/platform/inference/router/routing.py
- type: code
  path: portal/modules/research/tools/rag_mcp.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.685955
updated_at: 1784946220.685955
---

Two core chat models are pulled on the first `./launch.sh up` by the
`ollama-init` service in `deploy/portal-5/docker-compose.yml` (profile
`docker-ollama`). Its command runs two `ollama pull` calls before reporting
that core models are ready:

- `dolphin-llama3:8b` — the general-purpose default, set by `DEFAULT_MODEL` in
  `.env.example` (default `dolphin-llama3:8b`).
- `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` — the standby LLM
  router fallback. The router primary is `gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M`,
  which is the default of `_LLM_ROUTER_MODEL` in
  `portal/platform/inference/router/routing.py` and the value of
  `LLM_ROUTER_MODEL` in `.env.example`.

`nomic-embed-text` is not pulled. RAG, memory and Open WebUI embeddings are
the EmbeddingGemma 2 service on :8946: memory reads `EG2_EMBEDDING_URL`, RAG
and compliance read `VL_RETRIEVAL_URL` (default `http://localhost:8946/vl`).

`portal update` refreshes the model ids on the ollama backends in
`config/backends.yaml`. Library tags are passed to `ollama pull` when the
Ollama registry has a manifest; a 404 is skipped. A baked-context tag,
including a bare `:ctxNk` tag, is rebuilt from its base, and a `portal5/` tag
is skipped unless it pins a file. An `hf.co/` id is imported only when that model entry
pins `filename` and `sha256`. `nomic-embed-text` is not in that set.

## Why

A fresh machine needs a general chat model and a router standby before any
operator-time download. Embeddings are host EmbeddingGemma 2, not an Ollama
tag. The compose init container keeps that first-run pull on the normal `up`
path.
