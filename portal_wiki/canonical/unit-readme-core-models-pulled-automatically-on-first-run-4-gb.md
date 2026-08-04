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
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.685955
updated_at: 1784946220.685955
---

Three core models are pulled automatically on the first `./launch.sh up` by the
`ollama-init` service in `deploy/portal-5/docker-compose.yml`. Its command runs
three `ollama pull` calls before reporting that core models are ready:

- `dolphin-llama3:8b` — the general-purpose default, set by `DEFAULT_MODEL` in
  `.env.example` (default `dolphin-llama3:8b`).
- `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` — the standby LLM
  router fallback. The router primary is `gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M`,
  which is the default of `_LLM_ROUTER_MODEL` in
  `portal/platform/inference/router/routing.py` and the value of
  `LLM_ROUTER_MODEL` in `.env.example`.
- `nomic-embed-text:latest` — pulled as part of the core set. RAG embeddings are
  now served by the :8917 embedding server: `rag_mcp.py` and `memory_mcp.py` read
  `MLX_EMBEDDING_URL`, defaulting to `http://localhost:8917/v1/embeddings`.

The init service is the Docker-compose equivalent of the `_DEFAULT_MODELS` list in
`portal/platform/inference/cli/update.py`, which also opens with
`${DEFAULT_MODEL:-dolphin-llama3:8b}`, the abliterated Llama-3.2 GGUF and
`nomic-embed-text:latest`.

## Why

A fresh machine must reach a working minimum before any operator-time download
runs: a general chat model, a router standby and an embedding model guarantee
that routing, conversation and RAG all function on first boot. Pulling them in the
compose init container keeps the first-run pull inside the normal `up` path so the
stack is never brought up half-configured.
