---
id: unit-p5-roadmap-p5-fut-embed-001-embeddinggemma-migration-seed
kind: what
title: "P5_ROADMAP \u2014 P5-FUT-EMBED-001: EmbeddingGemma Migration Seed"
sources:
- type: code
  path: scripts/embedding-server.py
- type: code
  path: scripts/lib/services.sh
- type: code
  path: portal/modules/research/tools/rag_mcp.py
- type: code
  path: config/backends.yaml
last_generated_commit: 1896bb7da29dd96ff280b8ffb495519d507070ee
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.593046
updated_at: 1784946220.593046
---

P5-FUT-EMBED-001 is an open migration. Current production embedding is
`scripts/embedding-server.py`, which serves a sentence-transformers model —
`microsoft/harrier-oss-v1-0.6b` by default — on CPU on port 8917; the same
default is set in `scripts/lib/services.sh` and the launchd wrapper. The RAG MCP
(`portal/modules/research/tools/rag_mcp.py`) consumes the endpoint via
`EMBEDDING_URL` (default http://localhost:8917/v1/embeddings) and stores the
LanceDB index at `LANCE_DIR` (default `/Volumes/data01/portal5_lance`) built from
sources under `KB_SOURCES_DIR` (default `/Volumes/data01/portal5_kb_sources`),
which binds the index to the current embedding dimensionality.
`config/backends.yaml` carries an `embedding_candidates` block listing
`google/embeddinggemma-300M` and `Qwen/Qwen3-Embedding-0.6B`; the note for the
Qwen3-Embedding entry says its 4-bit variant is pre-positioned for a future
swap, so which candidate wins is still open scope. Migration requires
re-ingesting every RAG source under `KB_SOURCES_DIR`, a shadow-index A/B test,
and a rollback path with a feature flag in the RAG MCP.

## Why

Embedding swap is expensive because the LanceDB index encodes the embedding
dimensionality: switching models without re-indexing silently breaks retrieval,
and re-indexing every source is a full-corpus job. The migration therefore needs
a shadow-index A/B and a rollback window before the Harrier index is retired.
The code makes the dimension-binding the load-bearing constraint, and the
`embedding_candidates` block keeps the swap decision in config rather than
hardcoded.
