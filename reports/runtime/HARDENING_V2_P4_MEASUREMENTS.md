# TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2 — measurement phases

- **inputs**: HEAD of this task's branch, live host stack (:8942 VL server on
  HEAD code, :8917 embedding, Ollama holding ~5.4 GB)
- **host**: M4 Pro, 64 GB, darwin arm64
- **resolved-versions**: mlx 0.32.2, mlx-vlm 0.6.17, mlx-embeddings 0.1.0,
  transformers 5.16.1, torch 2.13.0, torchvision 0.28.0
- **timestamp**: 2026-09-01

---

## A5 — embed batch-size sweep (page images)

`scratchpad/a5_sweep.py` — 44 page images (NIST 800-82r3 architecture region +
synthetic figures), one warm call, then `/embed_batch` at batch sizes
1/2/4/8/12/16/24/32/48. VL server started with `VL_MAX_BATCH=64` so the server
does **not** sub-chunk — each POST is one padded forward pass.

| batch | wall (s) | per-item (s) | server RSS (MB) | Δ vs warm | ok |
|---|---|---|---|---|---|
| 1  | 1.77 | 1.77 | 2974 | +74   | ✓ |
| 2  | 3.49 | 1.75 | 2960 | +60   | ✓ |
| 4  | 6.92 | 1.73 | 1074 | −1826 | ✓ |
| 8  | 14.41 | 1.80 | 1213 | −1687 | ✓ |
| 12 | 22.75 | 1.90 | 561  | −2339 | ✓ |
| 16 | 30.30 | 1.89 | 877  | −2023 | ✓ |
| 24 | 45.54 | 1.90 | 1111 | −1789 | ✓ |
| 32 | 59.62 | 1.86 | 577  | −2323 | ✓ |
| 48 | 87.22 | 1.82 | 664  | −2236 | ✓ |

**Findings:**

1. **Per-item latency is flat at ~1.85 s across the whole range** — batch size
   is not a latency lever (same result the V4 `VL_RERANK_CHUNK` sweep found for
   reranking). Total wall time is linear in item count; large batches buy
   nothing.
2. **`ps rss` is not a usable memory-pressure signal on this host.** The model
   is mxfp8 2B (~2 GB of weights) yet the process reports 561–1213 MB *during*
   a 48-image forward — the deltas are physically impossible as "memory freed".
   MLX allocates Metal buffers that are not counted in RSS (the same
   macOS-accounting effect noted in `project_music_generation_uat_fixes`).
   Ollama held a steady 5372 MB throughout — no eviction, no contention.
3. **No failure, no OOM, no error at any batch size up to 48** page images in a
   single padded forward pass. The A1 concern ("46 page images survived at
   6.2 GB RSS … largest batch anyone has run") was reading the *cumulative
   ingest-process* RSS mid-run, not a per-batch spike; this sweep isolates the
   per-batch cost and finds none.

**Decision:** `VL_MAX_BATCH` (server) and `VL_EMBED_MAX_ITEMS` (client) set to
**24** — well below the tested-clean ceiling of 48, gives headroom for a larger
co-resident Ollama model, and still bounds the pathological case (a 500-page PDF
becomes 21 forwards of 24, not one 500-wide forward). Sized from the
no-observed-failure + linear-latency evidence, since the instrument (RSS) cannot
see a memory cliff on this platform. A future host with a slower / less
memory-elastic MLX build should re-run this sweep with `MEMORY_GRAPH` or GPU
pressure instrumentation before raising it.

## P4 — evaluation corpus

`tests/fixtures/rag_eval_corpus/` (committed: builder + `queries.yaml` +
`manifest.yaml`; the PDFs are not committed). **35 documents ingested:**
9 synthetic figure docs (provable prose-absence — the controls), 17 NERC CIP
standards, a NIST 800-82r3 architecture slice (26 pages, incl. Fig 20/21),
8 operator OT procedure docs (distractor pressure).

**Query set** (`queries.yaml`, 42 queries): `diagram_only` 21 · `prose_only` 16
· `mixed` 5. `target_file` on every query; diagram-only synthetic queries also
carry `target_page` — and a *text* hit on the right file does **not** count as a
diagram-only hit, the figure page must be returned.

**Ingest cost** (`RAG_MAX_PAGES=25`, `VL_EMBED_MAX_ITEMS=16`, host VL server):
35 files → 1257 text chunks + 480 page images in **1162 s (~19 min)**. The NERC
CIP docs dominate chunk count (~30–70 each). Per-query search cost is dominated
by the visual rerank — `RERANK_CHUNK=4` over ~30 candidates ≈ 8 VLM forwards
per query, ~15 s/query; the A3 `/health` model-id check adds one round trip.
42 queries ≈ 20 min. A full re-run of the regression set is ~40 min end to end.

## P5 — ranking

### RRF baseline — B1 confirmed, exactly

| category | n | recall@1 | recall@5 | MRR |
|---|---|---|---|---|
| diagram_only | 21 | **0.000** | 1.000 | **0.500** |
| prose_only | 16 | 0.625 | 0.938 | 0.769 |
| mixed | 5 | 0.600 | 1.000 | 0.800 |

**Every one of the 21 diagram-only queries returns the correct figure page at
rank exactly 2** — never 1, never 3. MRR is exactly 0.500. That is not "the
weighting needs tuning"; it is a deterministic artifact of the fusion function.

**Score dict** for `syn-pid-01` ("which control valve is air-to-open and
fail-closed?" — answer only on `pid_reactor_feed.pdf` p1):

```
TEXT   arm rank 0 -> RRF contribution 1/(60+0) = 0.016667   (a NIST chunk, wrong doc)
VISUAL arm rank 0 -> RRF contribution 1/(60+0) = 0.016667   (pid_reactor_feed p1 — CORRECT,
                                                             reranker_prob 0.6878)
       (wrong visual pages score 0.41 / 0.31 / 0.30 — the reranker is decisive and right)
```

The two rank-0 contributions are **identical**. `sorted(scores.items(), key=-v)`
is stable and the text arm populates the dict first, so the text row wins every
tie → text at rank 1, the correct figure at rank 2, for all 21. B1's
insertion-order diagnosis is **confirmed, not refuted** (P0's test: "if
contributions are not exactly equal, B1 is wrong" — they are exactly equal).
The Qwen3-VL reranker already produces the signal that fixes this
(`reranker_prob` 0.688 vs ≤0.41) and `_search` discards it.

### Fusion options

_(rerank_tiebreak / score_aware results appended when the variant runs finish)_

## P6 — max_pixels / DPI and coarse depth

_(pending)_
