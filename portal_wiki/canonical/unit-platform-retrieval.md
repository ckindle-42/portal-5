---
id: unit-platform-retrieval
kind: mixed
title: "Platform retrieval — the shared stage library"
sources:
- type: code
  path: portal/platform/retrieval/__init__.py
- type: code
  path: portal/platform/retrieval/chunking.py
- type: code
  path: portal/platform/retrieval/pages.py
- type: code
  path: portal/platform/retrieval/extraction.py
- type: code
  path: tests/fixtures/__init__.py
- type: code
  path: tests/fixtures/retrieval_legacy.py
- type: code
  path: tests/unit/test_retrieval_stage_parity.py
claims: []
confidence: high
tags:
- authored-v1
- platform
- retrieval
---

`portal.platform.retrieval` is the shared retrieval substrate — one
implementation of each retrieval primitive, composed more than one way.
TASK_RAG_COMPOSITION_SEAM_V1 established this seam: the general RAG and the
compliance engine differ by *composition, not configuration*, so a chunker bug
is fixed once and each consumer's index lifecycle stays independent.

## Why

`kb_search` / `kb_ingest` / `kb_search_all` serve fourteen persona workspaces
plus the router. Three of the four wanted substrate improvements (figure-scoped
visual index, docling `HybridChunker`, a BM25 arm, `contextualize`) invalidate
every index, so per-KB configuration cannot isolate them — defaulting to the new
behaviour changes all consumers at once, defaulting to the old one makes the
unfixed path permanent. And compliance does not need different *parameters*; it
needs different *stages* (temporal filtering before ranking, tier precedence,
enumeration over a register). Those are not knobs on `_search`. So: one
primitive, two compositions.

## Stages (Phase 2 — pure, no services)

- `chunking` — `chunk_fixed`, `chunk_structured`, `chunk` (strategy dispatch),
  `SECTION_BOUNDARY`, and the `CHUNK_SIZE` / `CHUNK_OVERLAP` / `CHUNK_STRATEGY`
  tuning constants. `fixed` is the default (structure lost against a
  docling-extracted corpus).
- `pages` — `render_pages` (pymupdf → PNG, records text-layer length in
  `_PAGE_TEXT_LEN`) and `figure_pages` (the deterministic sparse-text subset
  worth transcribing).
- `extraction` — `read_text`, delegating to `rag_mcp`'s docling-first chain.

Service-touching stages (embedding, store, fusion, pipeline) are extracted in
Phase 3.

## Compositions

- `portal.modules.research.tools.rag_multimodal` — the `kb_*` tools. Keeps thin
  aliases (`_chunk_fixed`, `_SECTION_BOUNDARY`, `_render_pages`, `_read_text`,
  …) for the transition; behaviour is byte-identical to pre-seam HEAD, proven
  by `tests/unit/test_retrieval_stage_parity.py` (function-level) and the
  Phase 4 end-to-end live-KB parity report.
- The compliance retrieval composition (Phase 7) — its own routes, its own
  tables namespaced away from `kb_*`, so a compliance re-ingest can never
  invalidate another consumer's index.

## Transitional

`tests/fixtures/retrieval_legacy.py` holds the pre-move stage bodies verbatim
(from commit `3de59b6c`) for the parity test to diff against. Both it and
`tests/unit/test_retrieval_stage_parity.py` are deleted in Phase 5 once the
Phase 4 end-to-end parity has also passed.

## Not here

Substrate *behaviour* changes — visual-index scope, the docling chunker, BM25,
`contextualize` — are a separate per-KB migration (`TASK_RAG_SUBSTRATE_MIGRATION`)
with per-consumer evaluation, because each one requires a re-ingest and changes
ranking. Phase 6 stamps the stage set into each KB's metadata so that migration
is caught by the same machinery that already catches an embedding-model swap.

One safety rule crosses the seam: `contextualize` (heading path into embedded
text) defaults off for any KB a security path can read — technique names in the
lineage must never reach the Bully's cousin engine.
