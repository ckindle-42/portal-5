---
id: unit-HOWTO-rag-embedding-reranking
kind: why
title: "HOWTO \u2014 RAG Embedding & Reranking"
sources:
- type: design
  path: docs/HOWTO.md
  section: RAG Embedding & Reranking
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.853027
updated_at: 1783195000.853027
---


Portal 5 v6.1+ uses Microsoft Harrier-0.6B as the primary embedding model for RAG, served by the `portal5-embedding` container (HuggingFace Text Embeddings Inference). This replaces the default Ollama `nomic-embed-text` with a SOTA embedding model that supports 32K context windows and 100+ languages.

**Architecture**: Open WebUI → portal5-embedding (:8917) → Harrier-0.6B embeddings → ChromaDB vector store → bge-reranker-v2-m3 cross-encoder reranking → results

**Configuration** (in docker-compose.yml, already set):
- `RAG_EMBEDDING_ENGINE=openai` — uses OpenAI-compatible API from TEI
- `RAG_OPENAI_API_BASE_URL=http://portal5-embedding:8917/v1`
- `RAG_EMBEDDING_MODEL=microsoft/harrier-oss-v1-0.6b`
- `RAG_RERANKING_MODEL=BAAI/bge-reranker-v2-m3`

**Fallback**: If the embedding service is unavailable, change `RAG_EMBEDDING_ENGINE=ollama` and `RAG_EMBEDDING_MODEL=nomic-embed-text:latest` in `.env` or docker-compose.yml to revert to Ollama-based embeddings.

**Memory impact**: The embedding service uses ~1.2GB. The reranker runs inside Open WebUI's process and uses ~0.6GB. Total: ~1.8GB always-on overhead.
