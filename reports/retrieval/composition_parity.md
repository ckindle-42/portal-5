<!--
evidence: TASK_RAG_COMPOSITION_SEAM_V1 Phase 4 — end-to-end composition parity
before:   3de59b6c4ea5c417bb3e35a3a3dc18a45c8031f4  (P1 — pre-seam retrieval code)
after:    a59d488f53b4733d9c43bf327e31a4bf62b1c368  (P3 — rag_multimodal composes the stage library)
host:     darwin 25.6.0, Apple Silicon
venv:     lancedb 0.37.1 · pyarrow 23.0.1 · httpx 0.28.1 · pymupdf 1.28.2 · docling 2.99.0 · transformers 5.16.1 · mlx-embeddings 0.1.0
vl server: :8942 ready — mlx-community/Qwen3-VL-Embedding-2B-mxfp8 (dim 2048, normalize=true) + Qwen3-VL-Reranker-2B-mxfp8
corpus:   9 deterministic two-page synthetic figure PDFs (tests/fixtures/rag_eval_corpus README builder), md5-stable
kb_id:    "parity" ingested into two separate PORTAL5_LANCE_DIR trees, one per commit
generated: 2026-09-02
-->

# Composition seam — end-to-end parity (P4)

`rag_multimodal`'s retrieval behaviour is **byte-identical** before and after the
composition-seam refactor (P2 + P3), proven on a live KB against the running
Qwen3-VL retrieval server.

## Method

The identical corpus (9 two-page PDFs, deterministic drawing code, byte-stable)
was ingested as `kb_id="parity"` under each commit into its own LanceDB
directory, then a fixed 10-query set was run. `scratchpad/p4_dump.py` recorded
every stable field; `p4_compare.py` diffed them. `ingested_at` is excluded (wall
clock, never contract); `image_path` is compared by basename (the two trees live
at different absolute paths).

## Result — every check byte-identical

| # | check | result |
|---|---|---|
| 1 | text `chunk_id` set (12 rows) | **identical** |
| 1 | visual `chunk_id` set (18 rows) | **identical** |
| 2 | embedding vectors, full float64 precision, all 30 rows | **identical** |
| 2 | text-row fields (`source_file`, `chunk_index`, `text`, `char_start`, `char_end`) | **identical** |
| 3 | visual `(source_file, page, image basename)` set | **identical** |
| 4 | search results for all 10 queries — order, `fused_score`, `reranker_prob`, `kind`, `page` | **identical** |
| 5 | `kb_ingest` response | **identical** |
| 5 | embedding-model stamp | **identical** |

`kb_ingest` response (both):
`{"kb_id": "parity", "files_ingested": 9, "chunks_added": 12, "pages_added": 18, "figtext_added": 0, "fts_index": false}`

Stamp (both): `{"embed_model": "mlx-community/Qwen3-VL-Embedding-2B-mxfp8", "vl_dim": 2048}`

## Query set

```
which valve is fail-closed on the reactor feed loop
anti-surge valve open condition for the recycle compressor
PLC-B7 IP address and rack slot in the Plant B ESP
one-way diode between the historian and the DMZ replica
alarm summary unacknowledged high pressure
SEL-751 feeder 12L4 instantaneous phase overcurrent pickup
locked-closed nitrogen valve to the reactor jacket
document control and management of change requirements
assembly muster area legend code
deaerator trend group scan rate and pressure span
```

Sample (query 1, top 3 — identical before/after):

| kind | source_file | page | fused_score | reranker_prob |
|---|---|---|---|---|
| visual | pid_reactor_feed.pdf | 1 | 0.65894 | 0.64227 |
| visual | locked_valve_schedule.pdf | 1 | 0.42255 | 0.40615 |
| visual | hmi_alarm_summary.pdf | 1 | 0.29384 | 0.27771 |

## Decision

Byte-identical on every axis → the refactor changed no retrieval behaviour.
Combined with the function-level parity harness
(`tests/unit/test_retrieval_stage_parity.py`), P4 clears the seam for P5 (retire
the legacy path). No substrate behaviour has changed; substrate improvements are
`TASK_RAG_SUBSTRATE_MIGRATION`, migrated one KB at a time with per-consumer
evidence.
