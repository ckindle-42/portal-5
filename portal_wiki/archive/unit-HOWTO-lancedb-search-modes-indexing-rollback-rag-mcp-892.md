---
id: unit-HOWTO-lancedb-search-modes-indexing-rollback-rag-mcp-892
kind: why
title: "HOWTO \u2014 LanceDB Search Modes, Indexing & Rollback (RAG MCP :8921)"
sources:
- type: design
  path: docs/HOWTO.md
  section: LanceDB Search Modes, Indexing & Rollback (RAG MCP :8921)
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.853765
updated_at: 1783195000.853765
---


**Search modes** — `kb_search` / `kb_search_all` accept `query_type`:

| query_type | What it does | When to use |
|---|---|---|
| `vector` (default) | Semantic similarity (bge embeddings) | Conceptual questions |
| `fts` | Native Lance BM25 keyword search | Exact terms: CIP-007 R2, CVE IDs, hostnames |
| `hybrid` | Vector + FTS fused with built-in RRF | Best of both; mixed queries |

`fts`/`hybrid` need an FTS index: re-ingest with `"fts": true` on `kb_ingest`.
`kb_search_all` silently falls back to vector for KBs without an index.
All modes keep the existing pipeline: 50 candidates -> bge reranker -> top_k.

**Vector indexing** — `kb_optimize` builds an IVF_PQ index (L2,
`num_partitions = min(512, sqrt(rows))`, `num_sub_vectors=64`). KBs under 256
chunks are skipped — brute force is already fast there. Run after large ingests:

```bash
curl -s localhost:8921/tools/kb_optimize -X POST \
  -H 'Content-Type: application/json' \
  -d '{"arguments": {"kb_id": "nerc-cip"}}'
```

**Version history & rollback** — every LanceDB write creates a version.
`kb_ingest` with `"rebuild": true` no longer drops the table; it tags the
current state (`pre-rebuild-<timestamp>`) and deletes rows, so a bad rebuild is
recoverable:

```bash
