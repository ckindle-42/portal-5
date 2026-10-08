---
id: unit-user-guide-how-it-works
kind: what
title: "USER_GUIDE \u2014 How It Works"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: scripts/eg2-embedding-server.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.516234
updated_at: 1784946220.516234
---

When you attach a document, Open WebUI chunks it at `CHUNK_SIZE` (1500
characters) with `CHUNK_OVERLAP` (100 characters) and embeds each chunk locally.
The embedding engine is not a chat model in Ollama: `RAG_EMBEDDING_ENGINE=openai`
points at the host-native EmbeddingGemma 2 service on port 8946
(`RAG_EMBEDDING_MODEL=google/embeddinggemma-2`), with the model card's search
prefixes applied through `RAG_EMBEDDING_QUERY_PREFIX` / `RAG_EMBEDDING_CONTENT_PREFIX`.
Search is hybrid — `ENABLE_RAG_HYBRID_SEARCH=true` fuses semantic and keyword results.
Because every endpoint (`host.docker.internal:8946` and the local Ollama host) is on
your machine, no document content leaves it.

## Why

The original unit credited `nomic-embed-text` in Ollama as the embedding model,
which the generated guide copied from an older stack. The deployment manifest
shows the RAG engine is the host-native embedder (now EmbeddingGemma 2 on port
8946), so the claim had to be corrected against the manifest rather than preserved. Grounding the chunk
sizes to `CHUNK_SIZE` and `CHUNK_OVERLAP` makes this unit's numbers enforceable
against the actual configuration.
