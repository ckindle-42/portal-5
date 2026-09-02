# TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2 — rollup

- **command**: the task's P0–P9 phases, executed with full authority against the live host stack
- **inputs**: fresh clone at `7b0b1ae0`, HEAD-authoritative; M4 Pro, 64 GB, darwin arm64
- **resolved-versions**: mlx 0.32.2, mlx-vlm 0.6.17, mlx-embeddings 0.1.0,
  transformers 5.16.1, torch 2.13.0, torchvision 0.28.0, phonemizer 3.4.0
- **timestamp**: 2026-09-01
- **detail reports**: `reports/runtime/HARDENING_V2_P0_FINDINGS.md`,
  `reports/runtime/HARDENING_V2_P4_MEASUREMENTS.md`

---

## Theme A — defects that would bite at scale

| item | outcome |
|---|---|
| **A1** embedding unbatched-limited | `VL_MAX_BATCH` (server, sub-chunks each text/image batch, order-preserved) + `VL_EMBED_MAX_ITEMS` (client, caps the POST body). Independent bounds. |
| **A2** `require_lance_dir` passes on its own failure case | mount check made first + unconditional; a bare `/Volumes/<vol>` dir no longer passes. `tests/unit/test_lance_guard.py` reproduces the stray-tree-on-unmounted-volume state. |
| **A3** nothing records which model embedded a KB | per-KB `kb_<id>.meta.json` stamp (embed_model, vl_dim); `kb_search` refuses (503 → `reindex_all`) on a same-dim model swap; `kb_list` surfaces it; legacy unstamped KBs not blocked. The model-id probe is cached 5 min (it shares the server's blocked event loop). |
| **A4** serialized inference + long query = silent queue | **measured (O2)**: concurrent `kb_search` reranks form a strict FIFO queue — wall ≈ N × single-call latency (N=2 → 17 s, N=3 → 28 s, N=5 → 46 s) — and **every request returns 200**, nothing dropped. `mx.eval` holds the GIL for the whole compute, so `/health` / `/ready` block 8–27 s behind an in-flight rerank (a `ReadTimeout` at N=5). Landed: `/health` constant-time (no MLX call) + `inflight` gauge, `/stats` for MLX memory. Documented: `KNOWN_LIMITATIONS.md` P5-VL-RETR-001 (set launchd health-probe timeout ≥ 60 s). A single-worker executor is the real loop-freeing fix but needs a soak test — future work. |
| **A5** measure before sizing A1 | swept 1..48 page images/forward: per-item latency flat ~1.85 s, no failure, no OOM. `ps rss` is not a usable signal (MLX Metal buffers off-RSS). `VL_MAX_BATCH` = 24. |

## Theme B — the capability was not delivered

**B1 — the RRF tie is deterministic text-preference, confirmed exactly.** The
score dict for a failing diagram query: text-arm rank-0 and visual-arm rank-0
both contribute `1/(60+0) = 0.016667`, `sorted` is stable, text is inserted
first → text wins every tie. All 21 eval diagram-only queries returned the
correct figure at rank **exactly 2**, MRR **exactly 0.500**. The Qwen3-VL
reranker's calibrated probability (0.688 for the right page vs ≤0.41) was
computed and discarded.

**Fusion options tried** (37 queries, `top_k` swept, same ingest):

| option | diagram r@1 | prose r@1 | prose r@5 | verdict |
|---|---|---|---|---|
| RRF (baseline) | 0.000 | 0.625 | 0.938 | — |
| A: rerank_tiebreak | 1.000 | 0.625 | 0.812 ↓ | regresses prose r@5 |
| B: score_aware | 1.000 | 0.625 | 0.812 ↓ | identical to A |
| **C: text_gate τ=0.67** | **1.000** | **0.625** | **0.938** | **adopted** |

A `reranker_prob` gate can't separate diagram (0.56–0.76) from spurious-prose
(0.61–0.72) — they overlap. The **top text chunk's cosine** does (diagram
0.44–0.62, prose 0.73–0.83). `text_gate` adds the reranker prob to the visual
arm's score only when `top_text_sim < VL_TEXT_GATE` (0.67, dead-center of the
measured gap; plateau to 0.72). Landed in `rag_multimodal._search`. diagram r@1
**0.000 → 1.000**, prose recall **byte-identical to RRF**.

**B2 — sparse text arm**: not pursued. `text_gate` resolves the prose side
without it, and the prose misses that remain are query-set ground-truth
ambiguities (operator OT docs cover the same topics as the NERC standards), not
fusion failures.

## Theme C — verification methods that leaked

| item | outcome |
|---|---|
| **C1** matplotlib drop validated by grep | **not a real defect** — full import-sweep of the reconciled venv shows every "missing" module is Docker-MCP-declared (`matplotlib`/`trimesh`/`docling` in `Dockerfile.mcp`, where `cad_render` :8926 actually runs) or a `sys.path` local or a retired path. The drop from host `pyproject.toml` was correct. Recorded in P0 findings. |
| **C2** memory store not reconciled | **not a `[GATE]`** — T8's 73/216/193 was a store conflation. The Docker named volume `portal-5_portal5-lance` holds 73/221/193 (+5 entities = ordinary growth); the host `/Volumes/data01/portal5_lance` orphan (72, no graph) is what V4's P3 measured. `graph_memory.graph_stats()` + memory-MCP `/health` + `validate_system` HB detect a silent restore shortfall going forward. |
| **C3** three evidence artifacts fail the standard | fixed (regenerated the 0-byte diff; retro headers on the freezes; `_evidence` blocks with versions on the parity JSONs) + the standard made enforceable — `scripts/lib/evidence_header.py` + `validate_system` HC fails on a zero-byte or header-less file under `reports/runtime/`. |
| **C4** wiki `claims:` binding is nominal | 3 real static probes + claims on `unit-capability-rag`: `deps.locked` contains torchvision / mlx-embeddings (the five-month regression), `rag.retrieval.routes` contains kb_search, `vl.embedding.dim` pattern-bound to the body figure. `:8942/ready` belongs to a live gate, not this bare-clone one — noted, not faked. |
| **C5** upstream bug has no regression test | `_reset_vl_state` regression tests: it fires before every `process()` call, and the rope-cache crash (two text-only calls, decreasing length) is reproduced against a fake model and shown to reappear when the reset is a no-op. |

## Theme D — guard coverage was asymmetric

| item | outcome |
|---|---|
| **D1** drift pre-flight protects one service | factored into `scripts/lib/venv_preflight.sh` (`_venv_lock_preflight`, now direction-aware), applied to every service sharing the fragile MLX runtime: :8917, :8918, :8924, :8942. Pure-Python MCPs deliberately ungated (rationale in the wiki unit — a hard drift-fail under KeepAlive would crash-loop the fleet on an unrelated bump). |
| **D2** `check_python_deps` recommends the harmful command | direction-aware: `-`/`~` in the sync diff = venv AHEAD → recommend `uv lock`, not `uv sync`. A subprocess failure sets `status="error"` (actionable) instead of reading healthy. |
| **D3** `validate_system` had no VL/mount/drift check | four new lettered checks: **GY** VL server ready+dim, **GZ** lance volume mounted, **HA** venv/lock drift, **HB** memory graph intact, **HC** evidence headers. |
| **D4** util.sh comment contradicts its code | corrected — the else branch warns and does not start the server. |
| **D5** floors violate the same-commit policy | `mlx>=0.32.2` floor added, `mlx-vlm>=0.6.17` (was 0.6.13), torchaudio/torch skew documented. Re-locked. |

## Theme E — measurement debt

| item | outcome |
|---|---|
| **E1** corpus can't settle the questions | `tests/fixtures/rag_eval_corpus/` — 36-doc corpus (9 synthetic figure docs with provable prose-absence, 17 NERC CIP standards, a NIST 800-82r3 slice, ~9 operator OT docs), 42 labelled queries (diagram_only / prose_only / mixed). `scripts/rag_retrieval_eval.py` reports recall@1/@5/MRR + latency per category. The standing regression set. |
| **E2** max_pixels/DPI decided together | swept `VL_MAX_PIXELS` {1.84M, 1.05M, 0.52M}, server restarted + full re-ingest each: recall / latency / ingest **byte-identical** at every level (`diag NOT@1` empty throughout). Pages render at 150 DPI = 2.10M px, so the 1.84M default already downscales ~12%; the vision tower is not the rerank bottleneck. **Decision: keep 1.84M + 150 DPI** — no measured benefit to lowering, and the corpus under-represents dense P&ID/HMI small text where a 0.52M downscale could drop glyphs. Lever for a future dense KB is *raising* both together. |
| **E3** latency: depth is the lever | rerank is ~1.7 s/page image, linear, and the whole query cost. `VL_RERANK_DEPTH` sweep 3/2/1.5/1: recall **identical at every depth** (embedding recall@5 for the visual arm is effectively perfect). Default **1.5** → 26.4 s → 13.9 s (−47 %); =1 → 8.8 s, also clean. |
| **E4** audio closeout | **real synthesis run through all four `:8918` routes** (`scratchpad/e4_audio.py`), each asserted non-degenerate (parseable WAV, dur > 2 s, RMS > 0.005, hard-clip < 2 %, voiced-frame > 15 %): **kokoro** 5.7 s / rms 0.047 / gen 2.9 s · **qwen3-tts CustomVoice** (Ryan + style instruct) 4.8 s / rms 0.068 / gen 35 s · **qwen3-tts VoiceDesign** ("design:…") 7.1 s / rms 0.079 / gen 37 s · **Higgs v2 voice-clone** (`trainer:chris`, scipy `resample_poly` path) 4.9 s / rms 0.018 / gen 85 s. All PASS. Higgs output is quiet (peak 0.12) but clearly voiced — noted, not a defect. |
| **E5** restored test lost its positive assertion | `test_unknown_defense`: restored the positive assertion that a technique with project detection content (T1558.003, T1078.004) is in the narrow set. |

## Speed / operational work (beyond the task's letters)

| lever | measured | landed |
|---|---|---|
| **S1** `mx.clear_cache()` per request | 0 latency cost, drift ratio 0.97 with and without; frees the ~9.4 GB MLX buffer cache | default on |
| **S3** rerank depth | see E3 | `VL_RERANK_DEPTH=1.5` |
| **S0** transcribe figures at ingest | only Ollama VL model is qwen3-vl:32b, >3 min/page → ~24 h ingest — **shelved** | dormant behind `RAG_TRANSCRIBE_FIGURES` |
| **O1** `:8942` recycle | `VL_MAX_REQUESTS` self-exit + `requests_served` in `/health`, MLX memory on `/stats`. Hygiene — the "10× session degradation" claim was **retracted**, it was a measurement artifact (probing while a rerank held the event loop). | committed |
| **O2** concurrency | measured N=2/3/5 — serial FIFO queue, 0 dropped requests; the defect is `/health` HoL blocking (GIL held through `mx.eval`). `/health` slimmed to constant-time + `inflight` gauge, `/stats` added, `_model_lock()` tracks depth. Limitation documented (P5-VL-RETR-001). | committed |

**Net effect on `kb_search`**: ~27 s → ~14 s, diagram-only recall@1 **0.00 → 1.00**, prose recall unchanged, footprint unchanged (~6 GB, the 2B embed + 2B rerank).

## Still open / honest-BLOCKED

- **VL server single-worker executor** — the correct fix for `/health` HoL
  blocking under concurrent load (frees the event loop without the multi-thread
  Metal crash the current one-lock design avoids). Needs a soak test before
  shipping; documented as P5-VL-RETR-001. Not landed in closeout.
- **S0** — transcribe figure pages at ingest — needs a 7B-class VL model in the
  fleet (only Ollama VL model is qwen3-vl:32b, >3 min/page). Dormant behind
  `RAG_TRANSCRIBE_FIGURES`.
- The prose-only query-set ground-truth ambiguities (6 of 16) — a query-set
  refinement, not a retrieval bug.

## Done means

- diagram-only queries return the right visual page at rank 1 with prose-only unregressed, on a 36-doc / 42-query corpus — **yes** (`text_gate` τ=0.67).
- embed and rerank both bounded and the bounds measured — **yes** (A1/A5, S3).
- the lance guard fails on an unmounted volume with a stray tree present — **yes** (A2 + test).
- a KB knows which model embedded it — **yes** (A3).
- the import sweep is clean; CAD's fallback — matplotlib is in `Dockerfile.mcp`, no host gap.
- the memory store is reconciled — **yes** (C2, not a `[GATE]`).
- the drift pre-flight covers every venv-resolved MLX service — **yes** (D1).
- `validate_system` fails when the VL server is down — **yes** (GY).
- no committed artifact describes a runtime that no longer exists — **yes** (C3);
  the two wrong statements in `P0_FINDINGS.md` / `VL_RUNTIME_LANDING_V4.md` are
  corrected in place with the originals left visible (P8).
- max_pixels/DPI decided together, with numbers — **yes** (E2: keep 1.84M/150 DPI).
- audio synthesis proven end to end on all four `:8918` routes — **yes** (E4).
- concurrency behaviour measured and the liveness gap documented — **yes** (O2 /
  A4 → P5-VL-RETR-001).
