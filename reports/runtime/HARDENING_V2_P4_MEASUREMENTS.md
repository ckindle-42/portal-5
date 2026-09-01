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

`tests/fixtures/rag_eval_corpus/` (committed: builders + query set + manifest;
the fetched PDFs are not committed). **36 documents:**

- **9 synthetic** (`build_synthetic.py`) — P&ID, network/ESP, HMI alarm/trend,
  relay settings, plot-plan legend, locked-valve schedule. Two-page: generic
  governance prose (page 1) + a single rendered figure (page 2) whose
  discriminating content — a valve tag, an IP, a setpoint, a legend entry —
  is **only** on the image. These are the controls: prose-absence is provable.
- **17 public NERC CIP standards** (CIP-002 … CIP-015) — fetched fresh.
- **1 NIST SP 800-82r3 architecture slice** (92 pages, SCADA/DCS/PLC +
  defense-in-depth figures) — fetched fresh.
- **9 internal OT/CIP procedure documents** — operator-provided, not committed;
  distractor pressure (prose-heavy, realistic).

**Query set** (`queries.yaml`, 43 queries):
`diagram_only` 22 · `prose_only` 16 · `mixed` 5. Each carries `target_file`; the
diagram-only synthetic queries also carry `target_page` (the figure page), and a
text hit on the right file does **not** count as a diagram-only hit — the figure
page must be returned.

## P5 — ranking

_(results appended after the fusion sweep completes)_

## P6 — max_pixels / DPI and coarse depth

_(pending)_
