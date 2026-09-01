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
text+image retrieval space — the Qwen3-VL embedding/reranker family — recovers
that. The shared text embedder (:8917) and reranker (:8925) stay up because the
memory subsystem and the Bully ORG projection still use them; only RAG's
*retrieval* moved to VL.

## Value

A question answered by a diagram now retrieves the diagram's page, not just
the surrounding prose, and every KB stays versioned and locally hosted.

## Migration

`rag_multimodal.reindex_all()` recreates each `kb_<id>` table and re-embeds its
text with the VL model (old tables are 1024-d, VL is `VL_EMBEDDING_DIM`). It ran
live against the deployed stack and was a no-op — the RAG store held no KBs — so
the re-index is complete. The text-only handler bodies are deleted; the
retrieval path is multimodal-only.

## Runtime-blocked

The VL retrieval *server* is code-complete and starts (`/health` responds), but
its model does not load: `mlx-embeddings` 0.1.0 (pinned in the `rag` extras)
does not recognise the Qwen3-VL-Embedding architecture, and no pre-converted
MLX build of Qwen3-VL-Embedding-2B exists on the Hub. Bringing `/embed` and
`/rerank` online is gated on an `mlx-embeddings` release with VL support, an
alternative VL-embedding runtime, or a local MLX conversion of
`Qwen/Qwen3-VL-Embedding-2B` — the inference-runtime re-evaluation the MCP
Fleet Overhaul program explicitly deferred. Until then `kb_ingest` / `kb_search`
return a descriptive honest-BLOCK error instead of crashing; with no KBs
ingested this blocks nothing. The `_embed_one` / `_score_pair` seams in
`scripts/vl-retrieval-server.py` are the only code that changes when a working
model lands. `curl :8942/ready` reports the load status.
