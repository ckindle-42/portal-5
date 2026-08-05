---
id: unit-user-guide-how-it-works
kind: what
title: "USER_GUIDE \u2014 How It Works"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: scripts/embedding-launchd-wrapper.sh
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
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
points at the host-native embedding server on port 8917 running the Harrier model
(`RAG_EMBEDDING_MODEL`). Search is hybrid — `ENABLE_RAG_HYBRID_SEARCH=true` fuses
semantic and keyword results. Because every endpoint (`host.docker.internal:8917`
and the local Ollama host) is on your machine, no document content leaves it.

## Why

The original unit credited `nomic-embed-text` in Ollama as the embedding model,
which the generated guide copied from an older stack. The deployment manifest
shows the RAG engine is the Harrier model served on port 8917, so the claim had
to be corrected against the manifest rather than preserved. Grounding the chunk
sizes to `CHUNK_SIZE` and `CHUNK_OVERLAP` makes this unit's numbers enforceable
against the actual configuration.
