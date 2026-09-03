<!--
evidence: TASK_RAG_COMPOSITION_SEAM_V1 — Phase 9 rollup
range:    58f011ec (pre-seam) .. 31515507 (P8)
seam commits: 3de59b6c P1 · fd3c9eab P2 · a59d488f P3 · 3adfe06b P4 · 8cdbf303 P5 · 7a8ea17c P6 · 491873ce P7 · 31515507 P8
host:     darwin 25.6.0, Apple Silicon
venv:     lancedb 0.37.1 · pyarrow 23.0.1 · httpx 0.28.1 · pymupdf 1.28.2 · docling 2.99.0 · transformers 5.16.1 · mlx-embeddings 0.1.0
vl server: :8942 — mlx-community/Qwen3-VL-Embedding-2B-mxfp8 (dim 2048) + Qwen3-VL-Reranker-2B-mxfp8
generated: 2026-09-02
-->

# Composition seam V1 — rollup

**The seam is composition, not configuration.** The retrieval substrate is now a
stage library (`portal.platform.retrieval`); `rag_multimodal` is one composition
of it, byte-identical to pre-seam HEAD; `compliance_retrieval` is a second,
writing to disjoint tables. No substrate *behaviour* changed — that is
`TASK_RAG_SUBSTRATE_MIGRATION`.

## Caller inventory (P0 + P1)

`kb_search` / `kb_ingest` / `kb_search_all` callers, and the argument shape each
sends:

| caller | kind | shape sent | accepted? |
|---|---|---|---|
| `context_inject.inject_retrieved_context` | router auto-context | **`{"query", "k"}`** — no `kb_id`, `k` not `top_k` | **NO → HTTP 400, silently recorded `outcome="miss"`** |
| `rag_mcp.py` | delegates `register_retrieval_routes` | n/a (registration) | — |
| `scripts/rag_retrieval_eval.py` | eval harness | `{kb_id, query, top_k}` via `_search` monkeypatch | yes |
| `tests/benchmarks/bench_daily_soak.py` | soak | `{kb_id, query}` | yes |
| `scripts/update_workspace_tools.py` | tool-list generator | n/a (names only) | — |
| personas: kbnavigator, factchecker, dailydriver, personalassistant, nemotronlightning, marketanalyst | `tools_allow` declarations | MCP bridge fills args | yes |

**One caller was broken** — the router's auto-context injector — and it was the
only one wired live (`auto-daily` had `auto_rag: true`, `_AUTO_RAG_ENABLED`
defaulted true). Auto-RAG had **never once worked**. See
`unit-known-limitations-auto-rag-silent-miss`.

## Auto-RAG `[GATE]` outcome

Resolved to **option (c)**: `_AUTO_RAG_ENABLED` defaults `false`, `auto_rag`
removed from `auto-daily`. The honest representation of today's behaviour — which
KB a workspace should draw from is unsettled, and enabling it is a real ~52 s/turn
latency change with cross-corpus exposure if routed to `kb_search_all`. The call
shape is corrected (`top_k`, optional `auto_rag_kb_id`) so it is ready when the
gate is answered.

## Stage → module map

| module | lines | stage |
|---|--:|---|
| `retrieval/chunking.py` | 89 | `chunk_fixed` / `chunk_structured` / `chunk`, `SECTION_BOUNDARY`, `CHUNK_*` |
| `retrieval/pages.py` | 54 | `render_pages`, `figure_pages`, `MAX_PAGES`, `FIGURE_PAGE_MAX_TEXT` |
| `retrieval/extraction.py` | 27 | `read_text` (docling-first chain via `rag_mcp`) |
| `retrieval/embedding.py` | 111 | `vl_embed` / `vl_embed_batch` / `vl_rerank` / `vl_model_id`, cache, dim guard, `VLUnavailableError` |
| `retrieval/store.py` | 168 | LanceDB tables + `list_kbs` + model/stage-set stamp; `prefix` param (P7) |
| `retrieval/fusion.py` | 191 | `rrf_fuse` (gated visual boost), `search_unified`, `fuse` dispatch; `VL_TEXT_GATE` |
| `retrieval/pipeline.py` | 274 | `Composition` + `ingest_document` / `search` / `search_all` / `reindex` |
| `research/tools/rag_multimodal.py` | 223 | composition #1 (was ~915) — `_composition()`, `_transcribe_page`, 3 route handlers |
| `compliance/tools/compliance_retrieval.py` | 123 | composition #2 — `compliance_` prefix, `compliance_ingest` / `compliance_search` |

## Parity

**Function-level (P2.2):** `chunk_fixed` / `chunk_structured` / `SECTION_BOUNDARY`
/ `figure_pages` / `chunk` dispatch — byte-identical to the pre-move bodies
(`tests/fixtures/retrieval_legacy.py`, from `3de59b6c`) across boundary-dense,
oversized-unit, fixed-fallback and empty inputs. Retired in P5 after P4.

**End-to-end on a live KB (P4):** identical 9-PDF deterministic corpus ingested
as `kb_id="parity"` under `3de59b6c` and `a59d488f`, against the live VL server.
Byte-identical on: text + visual `chunk_id` sets (12 / 18 rows), **all 30
embedding vectors to full float64 precision**, text-row fields, the visual
page/image set, **all 10 search queries** (order, `fused_score`, `reranker_prob`,
`kind`, `page`), the `kb_ingest` response, and the stamp. Detail:
`reports/retrieval/composition_parity.md`.

## Disjoint-table proof (P7)

`tests/unit/test_compliance_retrieval_seam.py`: the same corpus through both
compositions returns equivalent results while `kb_*` and `compliance_*` tables
(and `.meta.json` stamps) stay disjoint; a `rebuild` through the compliance
composition leaves every `kb_x` row **and** the `kb_` stamp byte-identical.

## Gate / complexity delta

| metric | before | after |
|---|--:|--:|
| validate checks | 210 | **211** (`HD` — KB stage-set stamp currency) |
| `check_spine_drift` claims | 44 | **51** (real `retrieval.stages` / `retrieval.compositions` bindings) |
| complexity `god_funcs` | 342 | **340** |
| complexity `god_lines` | 44,784 | **44,627** |
| complexity `prose` | 38,902 | 38,932 |

## honest-BLOCKED

None. Every phase landed with its gate green.

## Done

- `rag_multimodal` byte-identical to pre-refactor HEAD on a live KB — **yes** (P4).
- A second composition exists, runs, writes to disjoint tables — **yes** (P7).
- Stage set stamped so a future stage change invalidates its own index —
  **yes** (P6, `HD`).
- Every caller of the shared tools enumerated and sends an accepted shape —
  **yes** (P1, contract test).
- No substrate behaviour changed — **yes** (parity, both levels).
