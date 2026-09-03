---
id: unit-platform-retrieval-substrate-migration
kind: mixed
title: "Retrieval substrate migration — figure-scoped visual, docling chunker, BM25"
sources:
- type: code
  path: tests/fixtures/rag_eval_corpus/queries_lexical.yaml
- type: code
  path: tests/unit/test_retrieval_contextualize_gate.py
- type: code
  path: tests/unit/test_chunking_5tuple.py
- type: code
  path: tests/unit/test_retrieval_payload.py
claims:
- probe: retrieval.stage_set
  contains: visual_scope
- probe: retrieval.stage_set
  contains: contextualize
- probe: retrieval.stage_set
  contains: fts
- probe: retrieval.stages
  contains: extraction
confidence: high
tags:
- capability
- research
- authored-v1
---

`TASK_RAG_SUBSTRATE_MIGRATION_V1` closes the open defects in the shared
multimodal RAG (`portal.platform.retrieval`) and migrates the substrate one KB
at a time. Each stage change invalidates an index and re-ranks for a real
consumer, so every stage lands **available, not default**, gated by an env var
and recorded in the KB's stage-set stamp (check `HD`) — a KB indexed under a
different substrate is visible, never silent.

## The stages (each env-gated, default = pre-migration behaviour)

| stage | env | what it changes |
|---|---|---|
| P3.1 figure-scoped visual (O7) | `RAG_VISUAL_SCOPE=figures` | the visual arm indexes only pages under `FIGURE_PAGE_MAX_TEXT`, not every page. Measured on the compliance corpus: **435 → 16 visual rows**, no recall loss — 419 prose page-images were double-indexed. |
| P3.2 docling `HybridChunker` (O5) | `RAG_CHUNK_STRATEGY=docling` | `extraction.read_document` returns the `DoclingDocument`; `chunking.chunk_docling` chunks it layout-aware, carrying `prov.page_no` + heading path onto every row. Chunk tuples are 5-wide `(cs, ce, text, page, headings)` for every strategy. **Resolved the void `structured`-vs-`fixed` verdict in docling's favour on prose** (r@1 0.812 → 0.938; `prose-cip-07` rank 7 → 1). |
| P3.3 BM25 sparse arm (O4) | `RAG_FTS=1` + `RAG_BM25_WEIGHT` | `create_fts_index` at ingest; `_bm25_rows` RRF-merged into the text side (`rrf_fuse` / `text_gate` path only — not `search_unified`). Lexical-decoy set (`queries_lexical.yaml`) added first. **Prose r@1 → 1.000, decoy 7/8 → 8/8, 0 decoy false-positives.** |
| P3.4 `contextualize` (O6) | `RAG_CONTEXTUALIZE=1` | embeds heading path + text. **Default off, and check `HE` FAILs if any KB whose id names a discovery / corroboration path has it stamped on** — heading text carries technique names and the Bully's grading wall requires lineage never reach the cousin engine. Seeded-violation test in the style of the Bully's gate GP. |

## Payload (P2, no index change)

`fusion._text_payload` / `_visual_payload` are the single shaping point.
- **O2**: text hits carry `char_start` / `char_end` (stored at ingest, never
  returned before) and `page` (real under the docling chunker; `null`, never
  guessed, otherwise).
- **O3**: a page-image hit returns `text: null`, `content_available: false`, a
  `locator` and a `pointer_note` — not the `"[page image f.pdf p3]"` placeholder
  it used to ship as content, which `context_inject._extract_snippets` injected
  into the model's context as if it were readable. The injector now skips any
  `content_available: false` row.

## Migration unit

The compliance / OT RAG KB — 13 NERC CIP standards + a NIST SP 800-82r3 slice +
9 synthetic figure docs, with the 42-query `rag_eval_corpus` set and a committed
baseline. **Adopted for this KB:** figure-scoped visual + docling chunker +
BM25 (α ≈ 0.3) + `text_gate` at τ = 0.72 (default) — prose r@1 0.812 → 1.000,
`prose-cip-07` rank 7 → 1, lexical decoys 8/8, 0 decoy false-positives. The τ
sweep and the `unified`-fusion re-run both loop back to `text_gate` + BM25; the
diagram-lane number is a synthetic-corpus artifact (a "See the … drawing"
caption every fusion mode ranks above the figure image — see
[[unit-known-limitations-vl-text-gate-tuned-against-manufactured-collision]]).
Full per-query numbers and the per-stage adopt/revert decisions:
`reports/retrieval/SUBSTRATE_MIGRATION_V1.md`. Other kb_search workspaces are
unmigrated by absence of a corpus, not by choice.

## Why

The retrieval eval optimised `VL_TEXT_GATE` against an index the ingest doubled
(O7) and a chunker comparison docling's own chunker was never in (O5), so its τ
was internally valid and externally misleading — see
[[unit-known-limitations-vl-text-gate-tuned-against-manufactured-collision]].
Fixing the substrate rather than re-tuning the gate is what moved
`prose-cip-07`, the archetypal compliance question, from "not in the top 5 at
any τ" to rank 1. Nothing lands globally, because a win on one corpus is not
evidence for another — the stamp makes a half-migrated fleet impossible to
forget.
