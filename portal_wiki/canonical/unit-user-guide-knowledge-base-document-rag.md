---
id: unit-user-guide-knowledge-base-document-rag
kind: what
title: "USER_GUIDE \u2014 Knowledge Base & Document RAG"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: portal/modules/research/tools/rag_mcp.py
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.515291
updated_at: 1784946220.515291
---

Knowledge features are built on Open WebUI's RAG plus the pipeline's own
knowledge bases. The Open WebUI container is configured with
`RAG_EMBEDDING_ENGINE=openai` backed by the local Harrier embedding server,
`ENABLE_RAG_HYBRID_SEARCH=true`, and `CHUNK_SIZE`/`CHUNK_OVERLAP`; chat
attachments are chunked, embedded, and retrieved so answers are grounded in the
uploaded content. Persistent knowledge collections are managed through the
pipeline RAG MCP server (`kb_ingest`, `kb_search`, `kb_list`), which stores
vectors in LanceDB and reranks candidates via the MLX reranker. Nothing here
contacts a cloud service.

## Why

RAG is the one feature where the guide's "built into Open WebUI" claim conflated
a vendor UI with repository-owned plumbing. The repository actually owns two
layers: Open WebUI's attachment pipeline configured through the compose manifest,
and the LanceDB-backed knowledge bases exposed as MCP tools. Grounding this unit
to both lets a reader see which file governs each retrieval path.
