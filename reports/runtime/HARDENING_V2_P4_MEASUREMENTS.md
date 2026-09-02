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

## S1 — the VL server does NOT degrade over a session (earlier claim retracted)

An earlier draft of this doc reported a "~10× degradation" (warm embed 28 ms →
6–10 s). **That was a measurement artifact** and is retracted: those slow
readings were `curl` probes to `/health` or `/embed` issued *while a ~27 s
rerank was in flight* — the single event loop blocks every request behind the
in-flight model call (A4), so the probe *inherits* the rerank's latency. It was
never the server slowing down.

**S1 stress measurement** (`scratchpad/s1_stress.py`, 70 back-to-back reranks of
6 page images, nothing else touching `:8942`):

| `VL_MX_CLEAR_CACHE` | first-10 median | last-10 median | drift ratio | MLX cache held |
|---|---|---|---|---|
| **0 (off)** | 10.79 s | 10.48 s | **0.97** | 9408 MB (flat) |
| **1 (on)** | 10.84 s | 10.48 s | **0.97** | **0 MB** (freed each request) |

MLX `active_mb` / `cache_mb` / `peak_mb` were **flat the entire 70-rerank run**
with clear-cache off. No latency drift, no memory growth. So:

- `mx.clear_cache()` after each request (`VL_MX_CLEAR_CACHE`, staged in
  `vl-retrieval-server.py`) is **not a latency fix** — there is nothing to fix.
  Its value is **footprint**: it returns the ~9.4 GB MLX buffer cache to the OS
  between requests, which matters for coexistence with Ollama (~5.4 GB) + oMLX
  (~4.5 GB) + Docker on a 64 GB box. Whether it costs re-allocation overhead:
  the ON run showed **zero** overhead (identical latency, drift, active/peak memory) — so it defaults **on**.
- `VL_MAX_REQUESTS` self-recycle + launchd supervision (O1) are still worth
  having as **hygiene / a safety net**, but they are no longer urgent — there is
  no observed drift to bound.

Concurrency (A4), measured incidentally: while a rerank is in flight the server's
single event loop blocks **every** request including `/health` and `/ready` for
its full 15–27 s. Two overlapping `kb_search` calls: the second returns after
~2× a single search. The A3 model-id `/health` probe hit this (10 s timeout
behind a 20 s rerank) and is now cached (1 probe / 5 min) — but the OWUI-side
timeout must tolerate `N × ~20 s` for N concurrent RAG users, or `_search` needs
a "busy, retry" bound.

## S3 — rerank depth: the real latency lever (measured)

`_search` reranked `limit(top_k*3)` = 15 page images at `top_k=5` but the
response only uses `top_k*2` = 10. `VL_RERANK_DEPTH` (multiplier of `top_k`)
sweep, C1 fusion, 37 queries, `top_k=5`, same ingest:

| `VL_RERANK_DEPTH` | reranks | diagram r@1 | diagram r@5 | prose r@1 | prose r@5 | latency median |
|---|---|---|---|---|---|---|
| 3 (old default) | 15 | 1.000 | 1.000 | 0.625 | 0.938 | **26.4 s** |
| 2 | 10 | 1.000 | 1.000 | 0.625 | 0.938 | 17.5 s |
| **1.5 (new default)** | ~8 | 1.000 | 1.000 | 0.625 | 0.938 | **13.9 s** |
| 1 | 5 | 1.000 | 1.000 | 0.625 | 0.938 | 8.8 s |

**Recall is byte-identical at every depth** — the Qwen3-VL *embedding* recall@5
for the visual arm is effectively perfect (target page always in the cosine
top-5), so the reranker only reorders those. Reranking 15 was pure waste.

**Landed:** `VL_RERANK_DEPTH` default **1.5** → **26.4 s → 13.9 s (−47 %)** at
zero measured recall cost, with headroom above `top_k` in case a much larger KB
has weaker visual embedding recall@5. `VL_RERANK_DEPTH=1` (−67 %, 8.8 s) is
measured clean and available for latency-critical setups.

## S1/S3 combined — real-world `kb_search` latency

C1 (fusion, no speed cost) + S1 (`clear_cache`, no speed cost, −9.4 GB
footprint) + S3 (`VL_RERANK_DEPTH=1.5`): a `kb_search` on a KB with page images
goes **~27 s → ~14 s**, diagram-only recall@1 **0.00 → 1.00**, prose unchanged.

## S0 — transcribe figure pages at ingest (prototype, dormant)

`RAG_TRANSCRIBE_FIGURES=1` adds an ingest pass: each rendered page → vision LLM
→ structured transcript of every tag / address / setpoint / connection →
embedded into the **text** arm. Moves the figure-reading cost from every query
to once per page.

**Not viable with the current fleet.** The only vision model in Ollama is
`qwen3-vl:32b` (21 GB); measured at **>3 min for a single page** — a 480-page
corpus would be a ~24 h ingest. S0 is committed **dormant** and stays that way
until a 7B-class VL model (e.g. `qwen2.5-vl:7b`, `llava`, `moondream`) joins the
fleet, at which point re-run this measurement. With C1 + S3 already at ~9–14 s
and full recall, S0's marginal benefit does not justify a fleet addition now.

## P6 — max_pixels / DPI (E2)

**Swept `VL_MAX_PIXELS` ∈ {1 843 200, 1 048 576, 524 288} — server restarted per
level, full re-ingest each (25 pages/doc), 37 queries (21 diagram_only + 16
prose_only), `top_k=5`, RRF fusion, `mx.clear_cache()` on.**

| max_pixels | diagram r@1 | diagram r@5 | prose r@1 | prose r@5 | lat median | ingest |
|---|---|---|---|---|---|---|
| 1.84M (processor default) | 1.000 | 1.000 | 0.625 | 0.938 | 14.1 s | 1061 s |
| 1.05M | 1.000 | 1.000 | 0.625 | 0.938 | 14.1 s | 1055 s |
| 0.52M | 1.000 | 1.000 | 0.625 | 0.938 | 14.1 s | 1056 s |

`diag NOT@1` empty at every level. Results **byte-identical** across a 3.5× pixel
range.

**Reading.** `_render_pages` renders at **150 DPI** → letter pages are **1275×1650
= 2.10M px**, so the processor's 1.84M default already downscales ~12%. Dropping
the cap to a quarter of that (0.52M) changed **nothing** — not recall, not
latency, not ingest time. On Qwen3-VL-2B-mxfp8 on this hardware the vision-tower
cost for one page over this pixel range is a small fraction of a rerank; the LLM
forward (query × doc cross-attention) dominates and is ~constant. **max_pixels is
not a latency lever, and it is not an ingest-cost lever.**

**Decision (E2/P6): keep the 1.84M default and 150 DPI.** There is no measured
benefit to lowering either, and the eval corpus (synthetic figure docs + NERC
CIP text) under-represents dense small-text diagrams — P&ID tag bubbles, HMI
labels — where a downscale to 0.52M *could* drop glyphs below the tokenizer's
resolution. If a future dense-diagram KB shows a diagram recall regression, the
lever is **raising** render DPI and max_pixels together, not lowering them. S3
(`VL_RERANK_DEPTH`) is the latency lever; this knob is left at its safe default.

## O2 / A4 — concurrency + liveness under load (measured)

**N concurrent `/rerank` calls (5 page images each), one warm call first, `/health`
and `/ready` polled every 0.5 s throughout. VL server restarted clean, `mx.clear_cache()` on.**

| N | wall time | per-call latency | outcomes | `/health` during load | `/ready` during load |
|---|---|---|---|---|---|
| 2 | 17.2 s | 8.6 / 12.9 / 17.2 s | 2/2 HTTP 200 | med 8.3 s, max 16.7 s | 17.2 s |
| 3 | 27.6 s | 27.6 s (all) | 3/3 HTTP 200 | med 13.6 s, max 27.1 s | med 13.6 s, max 27.1 s |
| 5 | 46.0 s | 46.0 s (all) | 5/5 HTTP 200 | med 7.5 s, max 15.0 s, **1 ReadTimeout** | med 7.5 s, max 15.0 s, **1 ReadTimeout** |

**Reading.**
1. **The queue is correct.** Concurrent reranks serialize behind the single
   `asyncio.Lock` — wall ≈ N × single-call latency — and **every request returns
   200**. Nothing is dropped, no 5xx, no corruption. For a single-operator KB
   tool the realistic worst case (N=2–3 → 17–28 s) is within OWUI's tool timeout.
2. **Liveness is the real defect.** `/health` and `/ready` block 8–27 s behind an
   in-flight rerank, up to a `ReadTimeout`. `mx.eval` holds the GIL for the whole
   multi-second compute, so even a constant-time sync `/health` in FastAPI's
   threadpool cannot be scheduled. Slimming `/health` to touch **no** MLX runtime
   (moved `mx_mem` to `/stats`, added an `inflight` gauge) is still correct — it
   removes a second source of contention — but does not by itself unblock it
   (re-measured: identical profile).

**Landed:** `/health` constant-time + `inflight` gauge; `/stats` for MLX memory;
`_model_lock()` context manager tracks queue depth. **Documented:**
`KNOWN_LIMITATIONS.md` P5-VL-RETR-001 — set the launchd health-probe timeout
≥ 60 s so the serial queue never trips a false KeepAlive restart. **Not landed:**
a dedicated single-worker-thread executor (frees the loop without the multi-thread
Metal crash the current design avoids) — needs a soak test; future work.

## E4 — audio synthesis closeout (measured)

`scratchpad/e4_audio.py` — one ~15-word sentence through every `:8918` route,
each output parsed as WAV and asserted non-degenerate (dur > 2 s, RMS > 0.005,
hard-clip fraction < 2 %, voiced-frame fraction > 15 %).

| route | model | dur | RMS | peak | clip | voiced | gen | verdict |
|---|---|---|---|---|---|---|---|---|
| kokoro | `af_heart` | 5.7 s | 0.047 | 0.35 | 0.0 % | 44 % | 2.9 s | PASS |
| qwen3-tts CustomVoice | `Qwen3-TTS-…-CustomVoice-8bit`, voice `Ryan` + style instruct | 4.8 s | 0.068 | 0.50 | 0.0 % | 41 % | 35.4 s | PASS |
| qwen3-tts VoiceDesign | `Qwen3-TTS-…-VoiceDesign-8bit`, `design:<desc>` | 7.1 s | 0.079 | 0.67 | 0.0 % | 41 % | 36.6 s | PASS |
| Higgs v2 voice-clone | `higgs-audio-v2-3B-mlx-q8`, `trainer:chris` (scipy `resample_poly` ref path) | 4.9 s | 0.018 | 0.12 | 0.0 % | 48 % | 85.0 s | PASS |

All four produce valid, non-silent, non-clipped speech of plausible length. The
Higgs clone is quiet (peak 0.12, RMS 0.018) but clearly voiced (48 % of 20 ms
frames active) — a level quirk of the q8 clone at this reference, not a
degenerate/empty output. First-call model loads dominate the Qwen3/Higgs `gen`
times; the `_tts_lock` semaphore(1) serialises them (concurrent Metal command
buffers crash on Apple Silicon — pre-existing, intentional).

## O2 follow-up — single-worker MLX executor (soak-verified, landed)

The O2 measurement above left the liveness gap open on the grounds that
`run_in_executor` had previously crashed Metal. That precedent was a
**multi-worker** pool. A pool of exactly one persistent worker keeps every
`mx.*` call on one thread, in order — the same serialisation the inline path
gave the Metal stream — while taking the GIL-holding `mx.eval` off the event
loop. Landed as `_mx_pool` / `_run_mx`, reverting via `VL_MX_EXECUTOR=0`.

**Soak** (`scratchpad/vl_soak.py`, 12 rounds of one solo rerank + a concurrent
rerank/embed/rerank burst, `/health` polled every 250 ms throughout):

| | inline (before) | single-worker executor (after) |
|---|---|---|
| `/health` under load | med 8.3 s · max 27 s · ReadTimeouts | **med 2 ms · p95 4 ms · max 31 ms** |
| `/health` probes / errors | — | 1301 / **0** |
| model requests served | — | 49 / **0 failures** |
| Metal crash | (the risk being avoided) | **none** over 330 s mixed load |
| MLX memory after | — | active 5177 MB · cache 0 · peak 7212 MB (stable) |

**Verdict: PASS — shipped.** Rerank throughput is unchanged (still one GPU
stream, still FIFO); what changed is that the supervisor and any monitor can now
tell "busy" from "hung". `KNOWN_LIMITATIONS.md` P5-VL-RETR-001 updated: the
liveness half is resolved, the serial queue remains as an intended GPU bound.

## S0 revisited — 16-model, 4-round transcription bake-off (model chosen on evidence)

The V2 closeout shelved S0 as "not viable: the only Ollama VL model is
qwen3-vl:32b at >3 min/page (~24 h ingest)". Both halves of that were wrong —
`qwen3-vl:32b` was never the only option, and the constraint that S0 must run on
Ollama was an artifact of the prototype's `/api/generate` call, not architecture.
This host already runs five MLX services (`:8917/:8918/:8924/:8933/:8942`), and
`mlx-vlm` 0.6.17 ships native `paddleocr_vl`, `dots_ocr`, `got`, `florence2` and
`internvl_chat` architectures.

**Metric: ground-truth fact recall.** The synthetic figure builder
(`tests/fixtures/rag_eval_corpus/README.md`) returns, per figure, the exact
identifiers it draws — 45 facts over 9 pages. A transcript is scored on how many
it reproduces. Not a regex proxy, not a vibe.

| model | lineage | runtime | size | EXACT | norm | s/page | 480-pg |
|---|---|---|---|---|---|---|---|
| **qwen3-vl:4b-instruct-q4_K_M** | Alibaba | Ollama | 3.3 GB | **0.956** | 1.000 | 7.9 | 64 min |
| qwen3-vl:2b-instruct-q4_K_M | Alibaba | Ollama | 1.9 GB | **0.956** | 1.000 | **5.1** | **41 min** |
| glm-ocr:Q8_0 | Zhipu | Ollama | 1.6 GB | **0.956** | 1.000 | 5.8 | 46 min |
| Nanonets-OCR2-3B | Nanonets | Ollama | 2.8 GB | **0.956** | 1.000 | 9.8 | 78 min |
| qwen3-vl:8b-instruct-q4_K_M | Alibaba | Ollama | 6.1 GB | **0.956** | 1.000 | 12.9 | 104 min |
| minicpm-v4.5:Q4_K_M | OpenBMB | Ollama | 6.1 GB | 0.911 | 0.956 | 8.2 | 66 min |
| deepseek-ocr | DeepSeek | Ollama | 6.7 GB | 0.800 | 0.844 | **3.2** | 26 min |
| gemma4:e2b-it-qat | Google | Ollama | 4.3 GB | 0.356 | 0.400 | 9.5 | 76 min |
| granite3.2-vision:2b | IBM | Ollama | 2.4 GB | 0.111 | 0.111 | 34.5 | 276 min |
| gemma4:e4b-it-qat | Google | Ollama | 6.1 GB | 0.089 | 0.111 | 15.8 | 127 min |
| dots.ocr-GGUF:Q8_0 | rednote | Ollama | 3.2 GB | 0.000 | 0.000 | 13.2 | 105 min |

MLX runtime (separate round, generic prompt — see caveat below):
PaddleOCR-VL-8bit (0.9B) 0.978 norm @ 5.0s/page · Nanonets-OCR2-3B-8bit 1.000 @
8.5s · dots.ocr-4bit 0.422 @ 11.7s.

### Rounds 1-4 were partly measuring the harness. Three defects, all mine.

1. **`/api/generate` on a `{{ .Prompt }}` template.** Every model here — qwen3-vl,
   gemma4, glm-ocr, deepseek-ocr included — ships a 13-character Ollama template.
   On `/api/generate` that feeds the raw string in with **no chat markers at
   all**, so every instruct model was run un-templated. `/api/chat` lets the
   engine apply real chat formatting.
2. **Invented prompts for the specialists.** Each has a documented contract:
   glm-ocr `"Text Recognition:"`, deepseek-ocr
   `"<image>\n<|grounding|>Convert the document to markdown."`, PaddleOCR-VL
   `"OCR:"`, Nanonets its own long instruction, dots.ocr a layout-JSON prompt.
3. **Forced `temperature=0.0` over baked defaults.** qwen3-vl ships
   temp=1/top_k=20/top_p=0.95, gemma4 temp=1/top_k=64/top_p=0.95. Greedy decoding
   is also a classic repetition-loop trigger — DeepSeek-OCR's own reference
   inference ships an NGram logit processor (ngram_size=30, window_size=90)
   purely to suppress it.

**What the fair round overturned:**

| model | rounds 1-2 (broken harness) | round 5 (fair) |
|---|---|---|
| qwen3-vl:2b | **0.000** — "too small to resolve figures" | **0.956 EXACT @ 5.1s** — ties the 8B |
| deepseek-ocr | 0.000, 49s/page, 23-33k-char dumps | **0.800 EXACT @ 3.2s** — fastest tested |
| granite3.2-vision | 0.200, 147s/page | 0.111, 34.5s — verdict survives, latency was config |
| glm-ocr | "duplicates blocks, mangles LT-204" | **clean 283 chars, hyphens intact** — my prompt's fault |

The qwen3-vl:2b and deepseek-ocr reversals are the important ones: both were
written off on numbers produced by an un-templated, temperature-zero harness. The
gemma4 and granite verdicts survived correction, so those stand — but they stand
on evidence now rather than on a broken instrument.

**Caveat, recorded not hidden:** the MLX round (PaddleOCR-VL, dots.ocr, Nanonets)
still used the generic prose prompt, so PaddleOCR-VL's 0.978 @ 5.0s/page is
*understated* — its documented contract is `"OCR:"`. It was already the fastest
and smallest thing measured, and is the first candidate to revisit if ingest
wall-clock ever becomes the binding constraint.

**EXACT vs normalized.** The original metric normalized away whitespace and
commas, so it scored `"LT 204"` as a hit for `LT-204`. Every table above now
reports both. Even the winners sit at 0.956 EXACT vs 1.000 normalized — the gap
is the comma in `8,200`. An identifier search over the text arm sees the EXACT
column, so that is what the pick was made on.

### Why qwen3-vl:4b over glm-ocr, when glm-ocr is smaller and faster

Five models tie at 0.956 EXACT, so accuracy did not decide it. glm-ocr is 1.6 GB
vs 3.3 GB and 5.8 s vs 7.9 s/page — it wins on both of the stated criteria
(small, fast) at equal measured recall. That deserved more than the single-page
impression the first pick rested on, so both were re-run over all 9 figure pages
with glm-ocr on its **native** `Text Recognition:` contract:

| metric | glm-ocr:Q8_0 | qwen3-vl:4b |
|---|---|---|
| duplicate-line ratio | **0.377** | **0.006** |
| median transcript chars | 417 | 455 |
| pages describing connectivity | 2/9 | **5/9** |

glm-ocr repeats **37.7 % of its lines** even on its own contract — the clean
283-char page sampled during the first comparison was the outlier, not the rule.
Duplicated lines dilute the chunk embedding, which is the entire product of S0,
and they inflate the stored text without adding retrievable facts. qwen3-vl:4b
also describes component relationships on 5 of 9 pages ("V-204 Surge Drum is
connected to FV-101, which is connected to P-201 Feed Pump") where an OCR
transcriber structurally emits only the literal glyphs.

Recorded because the earlier version of this rationale cited a single page and a
duplication artifact that turned out to be caused by the wrong prompt. The
conclusion survived re-measurement; the evidence for it did not, and has been
replaced.

### NONE discipline is not a model-selection criterion

Every OCR specialist scored 0/4 on "reply NONE for a body-text page", which would
have disqualified them. That was the wrong question: it asks an LLM to decide
something the file format already answers. PyMuPDF reports each page's text-layer
length for free during render, so `_figure_pages()` selects transcription targets
deterministically (`RAG_FIGURE_PAGE_MAX_TEXT`, default 200 chars). A page with a
rich text layer is by definition already covered by its prose chunks. This
removes NONE discipline from selection entirely and cuts ingest cost further on a
text-heavy corpus, since most pages never reach the model at all.
