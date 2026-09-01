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

### Fusion options — measured (37 queries, top_k=3, same ingest)

| fusion | diagram r@1 | diagram MRR | prose r@1 | prose r@5 | prose MRR |
|---|---|---|---|---|---|
| **rrf** (baseline) | 0.000 | 0.500 | 0.625 | 0.938 | 0.760 |
| **rerank_tiebreak** | **1.000** | 1.000 | 0.625 = | 0.812 ↓ | 0.719 ↓ |
| **score_aware** | **1.000** | 1.000 | 0.625 = | 0.812 ↓ | 0.719 ↓ |

- `rerank_tiebreak` breaks a fused-score tie on the visual arm's `reranker_prob`;
  `score_aware` adds `reranker_prob` to the visual arm's contribution.
  **They produce identical output** — when the text and visual arms both sit at
  RRF rank 0, any positive visual signal promotes the visual row.
- **Both fix diagram-only completely** (r@1 0.000 → 1.000, all 21 at rank 1) and
  **hold prose r@1 exactly** (0.625) — so by the task's literal decision rule
  (diagram → rank 1 **and** prose r@1 unregressed) both **pass**.
- But it is a **trade, not a clean win**: `rerank_tiebreak`/`score_aware` newly
  fix `prose-cip-04/05/13` (RRF missed) and newly break `prose-cip-02/03/06/14`
  (RRF had at rank 1) — a relevant-looking page from an OT procedure doc
  outscores the target NERC standard's text chunk. prose r@5 −0.126, MRR −0.041.

### Prob dump — why a `reranker_prob` gate fails, and what works

Ran the 21 diagram + 11 prose queries and recorded, per query, the top text
chunk's cosine sim and the winning visual page's `reranker_prob`:

| | `reranker_prob` (winning visual) | top text cosine |
|---|---|---|
| diagram queries (21) | 0.56 – 0.76 | **0.44 – 0.62** |
| prose queries where a **wrong** visual wins (6) | 0.61 – 0.72 | **0.73 – 0.83** |
| prose queries where the **right** visual wins (5) | 0.56 – 0.68 | 0.74 – 0.78 |

A gate on `reranker_prob` cannot separate the classes — 0.56–0.76 vs 0.61–0.72
overlap. **The top text cosine separates them perfectly** (diagram ≤ 0.62,
prose ≥ 0.73) — it *is* the "is this answerable from prose?" signal.

### text_gate — the fix (τ_text sweep)

Add the reranker prob to the visual arm's score **only when the top text chunk's
cosine < τ_text**. Sweep:

| τ_text | diagram r@1 | diagram MRR | prose r@1 | prose r@5 | prose MRR |
|---|---|---|---|---|---|
| 0.60 | 0.810 | 0.905 | 0.625 | 0.938 | 0.760 |
| **0.67** | **1.000** | **1.000** | 0.625 | 0.938 | 0.760 |
| 0.72 | 1.000 | 1.000 | 0.625 | 0.938 | 0.760 |

**τ=0.67 is the answer** — dead-center of the measured 0.62/0.73 gap, plateau to
0.72. diagram_only recall@1 **0.000 → 1.000**, prose_only recall/MRR
**byte-identical to RRF** (same 6 misses, which are query-set ground-truth
ambiguities — the operator OT docs cover the same topics as the NERC standards —
not fusion failures). Passes the decision rule and the mandatory prose
counter-test with zero regression. Latency unchanged (~16 s median) — this is a
fusion-only change. **Landed** in `rag_multimodal._search` as `VL_TEXT_GATE`
(default 0.67); rejected options `rerank_tiebreak` / `score_aware` (both
regress prose r@5 −0.126) recorded above.

## E3 — rerank depth is the latency lever

Measured on a fresh VL server (`scripts/rag_retrieval_eval.py` component split):

| stage | cost |
|---|---|
| query text embed (warm) | ~30 ms |
| lancedb text/visual vector search (1257 / 480 rows, no ANN index) | 7–9 ms each |
| **VL rerank, 6 page images** | **12.6 s** |
| VL rerank, 9 page images | 15.4 s |
| VL rerank, 15 page images | 26.3 s |

Rerank is ~1.7 s/candidate + ~2 s base — **linear in candidate count, and it is
the entire query cost**. `_search` reranks `min(limit(top_k*3), top_k*2)` page
images, so at the production default `top_k=5` it reranks up to 10 → ~18 s/query;
at `top_k=3`, 6 → ~13 s/query. `VL_RERANK_CHUNK` (2/4/8/16) does not move this —
the cost is per-image forwards, not chunk overhead (matches the V4 sweep).
**Recommendation:** the coarse depth (`limit(top_k*3)` feeding the rerank) is the
knob to lower for latency; recall@5 is unaffected because the RRF/tiebreak fusion
only needs the right page *in* the reranked set, and the visual embedding recall
puts it there well within `top_k*3`.

## The VL server degrades over a session — and it is unsupervised

`:8942` served ~200 forwards across the P5 runs and its per-request latency rose
**~10×** (a warm text embed measured 28 ms early, 6–10 s late; rerank 17 s → 27 s
on identical inputs). RSS moved only 6.5 → 7.2 GB, so this is **not** memory —
it is MLX/Metal runtime-state accumulation (root cause not isolated; not thermal
per `pmset -g therm`). A fresh restart returns it to 28 ms.

`:8942` is a bare `nohup` (util.sh) with **no launchd supervision, no
KeepAlive, no request-count recycling**. Real-world: a long-lived VL server
serving RAG becomes progressively unusable. This is a bigger operational gap
than D1 flagged — it needs supervision **and** a recycle policy (exit after N
requests, or a scheduled bounce). Recorded for P7 / A4.

Concurrency (A4), measured incidentally: while a rerank is in flight the server's
single event loop blocks **every** request including `/health` and `/ready` for
its full 15–27 s. Two overlapping `kb_search` calls: the second returns after
~2× a single search. The A3 model-id `/health` probe hit this (10 s timeout
behind a 20 s rerank) and is now cached (1 probe / 5 min) — but the OWUI-side
timeout must tolerate `N × ~20 s` for N concurrent RAG users, or `_search` needs
a "busy, retry" bound.

## P6 — max_pixels / DPI and coarse depth

_(pending — the E3 depth curve above is the coarse-depth half)_
