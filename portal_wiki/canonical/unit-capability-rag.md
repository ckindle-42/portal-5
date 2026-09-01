---
id: unit-capability-rag
kind: mixed
title: "RAG MCP — multimodal LanceDB knowledge bases"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/research/tools/rag_mcp.py
- type: code
  path: portal/modules/research/tools/rag_multimodal.py
- type: code
  path: portal/modules/research/tools/test_rag_multimodal.py
- type: code
  path: scripts/vl-retrieval-server.py
- type: code
  path: config/inference/tools_manifest_rag_mcp.json
claims: []
confidence: high
tags:
- capability
- mcp
- research
---

# RAG MCP — multimodal LanceDB knowledge bases

## What

The RAG MCP (`portal/modules/research/tools/rag_mcp.py`, port 8921) manages
persistent knowledge bases in LanceDB. TASK_RAG_VISUAL_OVERHAUL_V1 replaced the
text-only retrieval stack with a multimodal one: the retrieval routes
(`kb_ingest` / `kb_search` / `kb_search_all`) live in `rag_multimodal.py` and
run on the Qwen3-VL retrieval server (`scripts/vl-retrieval-server.py`, a
FastAPI service exposing `/embed` and `/rerank` over a joint text+image
space). `rag_mcp.py` keeps the KB-lifecycle tools (`kb_list` / `kb_optimize` /
`kb_versions` / `kb_restore`) and registers the multimodal routes.

## How it's used

`kb_ingest` reads a source directory: text is chunked and VL-embedded, and for
every PDF the pages are additionally rendered to images (`pymupdf`) and
VL-embedded into a `kb_<id>_visual` sibling table — one ingestion, not a
separate visual opt-in. `kb_search` is multimodal by default: it retrieves
text chunks and page images for the query and fuses them with Reciprocal Rank
Fusion (the visual side is reranked by the VL reranker first), returning
results in the preserved shape plus a `kind` (`text` | `visual`) and `page`.
`kb_search_all` does the same across every KB. The tool contracts (args and
response keys) are unchanged so the ~10 caller workspaces keep working.

## Why it exists

Text-only retrieval discards the charts, one-line diagrams, HMI screenshots,
and table layout that carry the answer in P&IDs and NERC/CVE PDFs. A joint
text+image retrieval space — built on the Qwen3-VL embedding/reranker models
already in the pinned `mlx-embeddings` — recovers that. The shared text
embedder (:8917) and reranker (:8925) stay up because the memory subsystem and
the Bully ORG projection still use them; only RAG's *retrieval* moved to VL.

## Value

A question answered by a diagram now retrieves the diagram's page, not just
the surrounding prose, and every KB stays versioned and locally hosted.

## Migration

Existing text tables are 1024-d; the VL model is `VL_EMBEDDING_DIM`, so
`rag_multimodal.reindex_all()` recreates each `kb_<id>` table and re-embeds its
text with the VL model. This live re-index (and re-rendering source PDFs) is
the operator step: on this host it is honest-BLOCKED — `PORTAL5_LANCE_DIR` is
not mounted and the VL retrieval model is not downloaded. A pre-re-index
`$LANCE_DIR` snapshot is taken for operational safety; the design is forward,
with no text-only path retained.
