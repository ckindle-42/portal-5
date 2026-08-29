---
id: unit-capability-rag
kind: mixed
title: "RAG MCP \u2014 LanceDB knowledge bases"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/research/tools/rag_mcp.py
- type: code
  path: config/inference/tools_manifest_rag_mcp.json
claims: []
confidence: high
tags:
- capability
- mcp
- research
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# RAG MCP — LanceDB knowledge bases

## What

The RAG MCP (`portal/modules/research/tools/rag_mcp.py`, port 8921) manages
persistent knowledge bases stored in LanceDB. It is pipeline- and IDE-exposed
and is the repository-owned layer that complements Open WebUI's attachment
pipeline.

## How it's used

`kb_ingest` adds documents to a knowledge base, `kb_search` and `kb_search_all`
retrieve against it (reranking candidates via the MLX reranker), `kb_list`
enumerates bases, and `kb_optimize`, `kb_versions`, and `kb_restore` manage the
store — compaction, version history, and rollback.

## Why it exists

Persistent knowledge collections are repository-owned plumbing, distinct from
the per-chat attachment path that Open WebUI handles. Owning the persistent
layer as an MCP means a base survives across chats, is versioned, and is
queried by a typed retrieval tool rather than by re-uploading content each
session. The rerank step keeps retrieval two-stage: candidate search, then a
dedicated reranker.

## Value

A knowledge base ingested once is available to every later conversation with
grounded, reranked answers, and the version tooling means a bad ingestion is a
`kb_restore` away. Nothing here contacts a cloud service — vectors and
retrieval stay local.
