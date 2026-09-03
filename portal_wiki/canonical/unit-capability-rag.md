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
- type: code
  path: portal/platform/lance_guard.py
claims:
- probe: modules.enabled
  contains: research
# torchvision absent from the lock is the exact regression that carried a wrong
# VL diagnosis for five months (C4). mlx-embeddings is the qwen3_vl carrier.
- probe: deps.locked
  contains: torchvision
- probe: deps.locked
  contains: mlx-embeddings
# retrieval routes must stay owned by rag_multimodal, not the text-only handler.
- probe: rag.retrieval.routes
  contains: kb_search
# the embedding dim figure in the body is the only copy; drift renames the unit.
- probe: vl.embedding.dim
  pattern: "embedding dim **{value}**"
# SEAM V1: rag_multimodal must stay a composition of portal.platform.retrieval,
# not re-absorb the substrate. Fails the census if it stops composing.
- probe: retrieval.compositions
  contains: portal/modules/research/tools/rag_multimodal.py
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
FastAPI service exposing `/embed`, `/embed_batch`, and `/rerank` over a joint
text+image space). `rag_mcp.py` keeps the KB-lifecycle tools (`kb_list` /
`kb_optimize` / `kb_versions` / `kb_restore`) and registers the multimodal
routes.

## How it's used

`kb_ingest` reads a source directory: text is chunked and VL-embedded, and for
every PDF the pages are additionally rendered to images (`pymupdf`) and
VL-embedded into a `kb_<id>_visual` sibling table — one ingestion, not a
separate visual opt-in. `kb_search` is multimodal by default: it retrieves
text chunks and page images for the query and fuses them with Reciprocal Rank
Fusion (the visual side is reranked by the VL reranker first), returning
results in the preserved shape plus a `kind` (`text` | `visual`) and `page`.
The fusion is **text-gated** (`VL_TEXT_GATE`, default 0.72 cosine): plain RRF
ties a top text chunk and a top page image at exactly `1/60` and text always
wins on insertion order, so a diagram-only query never surfaced its figure. The
VL reranker's calibrated probability is added to the visual arm's score **only
when the top text chunk's own similarity is below the gate** — i.e. only when
the query is not answerable from prose. Measured: diagram-only recall@1
0.00 → 1.00, prose recall unchanged.
`kb_search_all` does the same across every KB. The tool contracts (args and
response keys) are unchanged so the ~10 caller workspaces keep working.

## Composition seam

TASK_RAG_COMPOSITION_SEAM_V1 extracted the retrieval substrate — chunking, page
rendering, extraction, the VL client, the LanceDB store, fusion, and the
pipeline entry points — into the shared stage library
`portal.platform.retrieval` (see `unit-platform-retrieval`). `rag_multimodal` is
now one *composition* of those stages: `_composition()` wires them and the four
route handlers keep the HTTP concern. Behaviour is byte-identical to pre-seam
HEAD — proven at function level and end-to-end on a live KB
(`reports/retrieval/composition_parity.md`). The compliance engine is a second
composition with its own `compliance_*` tables.

Each KB's meta stamp records the **stage set** (chunker, chunk size/overlap,
figure-page policy, transcription, fusion mode) as well as the embedding model;
`kb_search` rejects a KB whose stamped stage set differs from the running
composition (validate check `HD` reports a half-migrated fleet). Substrate
*behaviour* changes — figure-scoped visual index, the docling chunker, a BM25
arm, `contextualize` — are a **separate per-KB migration**
(`TASK_RAG_SUBSTRATE_MIGRATION`), not a config flag, because each requires a
re-ingest.

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

## Runtime

The VL retrieval server loads and serves. `TASK_VL_RUNTIME_LANDING_V4` landed it.

- **Models:** `mlx-community/Qwen3-VL-Embedding-2B-mxfp8` (embed) and
  `mlx-community/Qwen3-VL-Reranker-2B-mxfp8` (rerank), overridable via
  `VL_EMBED_MODEL` / `VL_RERANK_MODEL`. Genuine MXFP8
  (`{'group_size': 32, 'bits': 8, 'mode': 'mxfp8'}`).
- **Resolved versions:** `mlx-embeddings 0.1.0` (ships the `qwen3_vl` module),
  `mlx 0.32.2`, `mlx-vlm 0.6.17`, `transformers 5.16.1`, `torch 2.13.0`,
  `torchvision 0.28.0`.
- **Measured:** embedding dim **2048** (`VL_EMBEDDING_DIM`);
  `model.args.normalize` is **True**, so `/embed*` returns unit vectors and the
  server never re-normalizes. `/ready` reports `ready`, `dim`, and `normalize`;
  `/health` is non-empty.
- **The real cause chain of the earlier block** (three snapshots, one symptom —
  see KNOWN_LIMITATIONS): a **missing `torchvision`** on top of a hand-patched
  venv the lock did not describe, plus a reranker seam that called the embedding
  `/embed`. transformers 5.x gates `AutoImageProcessor` behind
  `@requires(backends=("vision",))` where `vision` == torchvision, and the
  Qwen3-VL processor constructs it — even though preprocessing itself runs on
  the PIL path (`Qwen2VLImageProcessorPil`), so the torchvision *version* is
  inert to output. The earlier "architecture not supported / no MLX build
  exists" claim was **wrong** — 0.1.0 already had `qwen3_vl`; it was
  torchvision, not the model.
- **Video is unsupported** on this runtime
  (`_UnsupportedVideoProcessor.__call__` raises); do not inherit the model
  card's video claim.
- If retrieval is down, `kb_ingest` / `kb_search` return a plain **503** quoting
  the upstream error and pointing at `:8942/ready`.
- The `_embed_items` / `_score_documents` seams in
  `scripts/vl-retrieval-server.py` isolate the mlx-embeddings API; a version
  bump touches only them.
