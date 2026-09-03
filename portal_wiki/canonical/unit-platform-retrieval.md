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
  path: portal/platform/retrieval/embedding.py
- type: code
  path: portal/platform/retrieval/store.py
- type: code
  path: portal/platform/retrieval/fusion.py
- type: code
  path: portal/platform/retrieval/pipeline.py
- type: code
  path: portal/modules/compliance/tools/compliance_retrieval.py
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

## Stages

Pure (Phase 2 — no services):

- `chunking` — `chunk_fixed`, `chunk_structured`, `chunk` (strategy dispatch),
  `SECTION_BOUNDARY`, and the `CHUNK_SIZE` / `CHUNK_OVERLAP` / `CHUNK_STRATEGY`
  tuning constants. `fixed` is the default (structure lost against a
  docling-extracted corpus).
- `pages` — `render_pages` (pymupdf → PNG, records text-layer length in
  `_PAGE_TEXT_LEN`) and `figure_pages` (the deterministic sparse-text subset
  worth transcribing).
- `extraction` — `read_text`, delegating to `rag_mcp`'s docling-first chain.

Service-touching (Phase 3):

- `embedding` — the Qwen3-VL retrieval-server client (`vl_embed` / `vl_embed_batch`
  / `vl_rerank` / `vl_model_id`), the request-size cap, the `_MODEL_ID_CACHE` TTL,
  the dim guard, and `VLUnavailableError`.
- `store` — LanceDB table open/create, the KB list, and the model + stage-set
  stamp sidecar (`read_stamp` / `write_stamp` / `assert_embedding_space`). The
  stamp records the embedding model AND the stage set (chunker, chunk
  size/overlap, figure-page policy, transcription, fusion mode); `search`
  rejects a KB whose stamped stage set differs from the running composition
  (503, same class as a model swap), and validate check `HD` reports a
  half-migrated fleet.
- `fusion` — `rrf_fuse` (RRF text/visual with the gated visual boost),
  `search_unified` (one cross-encoder pass), and `fuse` dispatch on the mode.
  `VL_TEXT_GATE` τ=0.72 and the mode constants live here.
- `pipeline` — the `Composition` dataclass and the four entry points
  `ingest_document` / `search` / `search_all` / `reindex`, free functions over a
  composition. The HTTP concern (JSONResponse, 503/500/404 mapping) stays in the
  route handlers; `UnknownKBError` is raised where `_search` returned an in-body
  404.

## Compositions

- `portal.modules.research.tools.rag_multimodal` — the `kb_*` tools. ~260 lines:
  `_transcribe_page` (S0), a per-call `_composition()` that wires the stages, and
  the four route handlers (which keep the HTTP concern — JSONResponse, the
  503/500/404 mapping). Behaviour is byte-identical to pre-seam HEAD, proven at
  function level (the P2 parity harness) and end-to-end on a live KB
  (`reports/retrieval/composition_parity.md`, P4). The transitional aliases and
  the legacy-body fixture were removed in P5 once both parities were green.
- `portal.modules.compliance.tools.compliance_retrieval` (Phase 7) — a second
  composition of the same stages, bound to the `compliance_` table prefix and
  its own `compliance_*.meta.json` stamps, on routes `compliance_ingest` /
  `compliance_search` on the compliance MCP. No compliance semantics yet
  (`TASK_COMPLIANCE_ENGINE` lands on this scaffold). Acceptance: the same corpus
  through both compositions returns equivalent results while writing to disjoint
  tables, and a `rebuild` through the compliance composition leaves every `kb_*`
  table and stamp byte-identical
  (`tests/unit/test_compliance_retrieval_seam.py`). The `store` stage carries a
  `prefix` parameter (default `kb_`) to make this possible; nothing else in the
  library needed a change.

## Not here

Substrate *behaviour* changes — visual-index scope, the docling chunker, BM25,
`contextualize` — are a separate per-KB migration (`TASK_RAG_SUBSTRATE_MIGRATION`)
with per-consumer evaluation, because each one requires a re-ingest and changes
ranking. The stage set is stamped into each KB's metadata (P6) so that migration
is caught by the same machinery that already catches an embedding-model swap.

One safety rule crosses the seam: `contextualize` (heading path into embedded
text) defaults off for any KB a security path can read — technique names in the
lineage must never reach the Bully's cousin engine.
