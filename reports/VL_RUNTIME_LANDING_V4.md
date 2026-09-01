# VL Runtime Landing V4 — Rollup

Executed 2026-09-01 against the live host. Full authority; `honest-BLOCKED` over
faked-green.

## P0 — fingerprint & the sync-drift mechanism

`reports/runtime/venv-working-20260901T084333.txt` (committed) is the only
description of the working runtime that existed. Key: **live torch was 2.13.0,
not V4's assumed 2.11.0** → `torchvision==0.28.0` matches with no torch move.

**Sync-drift mechanism:** nothing suppresses the sync. The wrapper used a plain
`uv run --project` (no `--frozen`/`--no-sync`); no `[tool.uv]`, no `UV_*` env.
`uv lock --check` passed; `uv sync --all-extras --check` would have uninstalled
133 / installed 74 (`mlx-embeddings 0.1.0→0.0.5`, `mlx 0.32→0.31`,
`torch 2.13→2.11`). The live `:8917` process simply predated the hand-patch —
the next launchd restart (or the pre-commit hook's own `uv run pytest`) would
have destroyed the runtime. Pinning alone was **not** sufficient; the wrapper
now runs `--no-sync` behind a `uv sync --frozen --check` pre-flight.

The venv/lock divergence was **far larger than V4 modeled** (250 vs 225 pkgs,
~117 shared). Operator decision: reconcile the **runtime-critical set only**;
let `uv sync` drop the 133 undeclared pip-installs (a full pyannote/lightning
diarization stack nothing imports, optuna, sklearn, numba, matplotlib,
mlx-whisper, bench tooling). Audio verified separately in P5.

## The three-way error-string record (the lesson)

| source | string |
|---|---|
| T9 commit + wiki | `'NoneType' object has no attribute 'model_type'` |
| V3 from 0.0.5 source | `ValueError: Model type qwen3_vl not supported.` |
| **live host (P0.4, verbatim)** | `ImportError: AutoImageProcessor requires the Torchvision library…` |

Each was correct for a different environment snapshot and pointed at a different
remedy. The record carried the wrong one for ~5 months. **A paraphrased error
string is worse than none — it fossilises a diagnosis of a runtime that no
longer exists.** Every phase captured the verbatim traceback *with* the resolved
versions beside it (`reports/runtime/`). Written into
`unit-known-limitations-vl-retrieval-runtime`.

## P0.5 — accidental-sync severity

`mlx-embeddings 0.0.5` **+** `mlx 0.31.2` both **load and forward** the on-disk
`mode: mxfp8` model (throwaway env). So an accidental `uv sync` kills the VL
path (certain) but **`:8917` survives**. Less severe than feared.

## P1 — torchvision + lock reconciliation

- `torchvision==0.28.0` added to `apple-silicon` (pinned: `requires torch==2.13.0`,
  the live torch; preprocessing runs on the PIL path so the version is inert).
- Floors → live: `mlx-embeddings>=0.1.0`, `mlx-lm>=0.31.3`, `mlx-vlm>=0.6.13`,
  `torch>=2.13.0`, `torchaudio>=2.11.0`, `transformers>=5.16.1` (deliberate,
  from 5.15.0), `huggingface_hub>=1.9.1`, `pymupdf>=1.28.2`, `lancedb>=0.37.1`,
  `phonemizer>=3.4.0` (P5 regression fix).
- `mlx-audio <0.5.0` cap **removed** (reason void); resolver kept 0.4.8.
- `mcp>=2.0.0,<3.0.0` annotated with a cap receipt + sunset; policy comment at
  the top of the dependency section.
- `en-core-web-sm` declared (`[tool.uv.sources]` URL) so sync stops uninstalling it.
- **P1.4 gate:** the reconciled lock resolved into a scratch env; the post-`uv
  sync` project venv is **byte-identical** to it. Zero unintended differences.
- **P1.5:** `embedding-launchd-wrapper.sh` → `uv run --no-sync` + drift pre-flight;
  `scripts/lib/util.sh` VL readiness gate is now version-aware
  (`mlx_embeddings.models.qwen3_vl` + `torchvision` find_spec).

## P2 — blocker gone

`mlx-community/Qwen3-VL-Embedding-2B-mxfp8` and `-Reranker-2B-mxfp8` load.
`model.args.normalize == True`. Embedding **dim 2048** == `VL_EMBEDDING_DIM`.
Ranking sane (cos(query, on-topic)=0.71 vs off-topic 0.19); rerank shape `(N,)`.

## P3 — parity: IDENTICAL, no re-embed

`:8917` restarted on the reconciled venv. `scripts/embedding_parity_probe.py`
over a committed 55-row corpus (`tests/fixtures/embedding_parity_probe.jsonl`):
**self_cos min 1.000000, top1 agreement 1.0**. `models/qwen3.py` is byte-identical
0.0.5→0.1.0 and here the embedding model version did not even change. **No
re-embed.** Memory graph (72 rows, 1024-d, unchanged) and the RAG store (0
tables) are both valid. SA5 Arm A baseline is noted void (runtime moved) — not
touched.

## P4 — store & volume hygiene

`/Volumes/data01/portal5_lance` did not exist (only a presnapshot tgz at the
volume root). Restored from `portal5_lance_presnapshot_20260831T233605.tgz`
(kept intact); fresh `portal5_lance_snapshot_vl_landing_*.tgz` taken.
`portal/platform/lance_guard.py::require_lance_dir` now gates
`graph_memory._conn` / `rag_mcp._get_db` / `rag_multimodal._get_db` on the
volume being mounted. `~/.portal5/embedding-venv` (880M dead stub) removed.

## P5 — audio

One regression, fixed forward (**no `[GATE]`**): the sync reverted
`phonemizer 3.4.0→3.3.0`; 3.3.x's `EspeakWrapper` has no `set_data_path`, which
`misaki.espeak` calls at import → all Kokoro TTS 503'd. Floor → `>=3.4.0`.

Verified on the reconciled venv: Kokoro TTS (real synth via :8918, 4.05s
non-silent), Parakeet-TDT-v3 (real round-trip: "Portal 5 Audio, verified after
the runtime landing."), Sortformer diarizer loads via `mlx_audio.vad`,
`mlx_audio.{tts,stt,vad}` / `qwen3_tts` / `higgs_audio` / `mlx_lm` /
`scipy.signal` import OK. mlx-audio stayed 0.4.8 so §1.5's changed modules did
not actually move. Higgs voice-clone and Qwen3-TTS synth not exercised (imports
+ model presence confirmed).

## P6 — VL server, rewritten to the verified API

`scripts/vl-retrieval-server.py` full replacement. Live-verified on :8942:
`/ready` dim 2048 normalize true; `/embed_batch` mixed text+image → `(3, 2048)`;
`/rerank` 5 docs @ chunk 4 → relevant text 0.73, matching image 0.72, unrelated
0.13; empty item → 400 (not embedded as `"NULL"`). Text and image items batched
separately; instruction on the query only; `len(scores)==len(documents)`
asserted; tempfiles unlinked in `finally`; one `asyncio.Lock`, no
`run_in_executor`; non-empty `/health`; no video claim.

**Two library bugs worked around** (both in `unit-known-limitations-…`):
`mlx_embeddings.load()`'s `allow_patterns` omits `chat_template.jinja` → full
`snapshot_download` first; `compute_qwen3_vl_hidden_states` only clears
`language_model._position_ids` on pixel-value calls → server clears it before
every `process()` ("Too many indices for array with 2 dimensions").

`rag_multimodal.py` client seam: batched `/embed_batch` (image paths, not
base64), one chunked `/rerank`, dim guard, instruction on query only, same
batching in `reindex_all()`, `_VLUnavailableError` → 503 quoting the upstream
error + `/ready`.

## P7 — tests & gates

- `tests/unit/test_vl_retrieval_server.py` — FakeModel/FakeProcessor seam
  contract (8 tests): list→embed `(N,dim)`; dict+documents→rerank `(len,)`;
  text/image never share a batch; docs carry no instruction; length mismatch
  raises; tempfiles unlinked incl. on exception; normalize read once. (Pre-P6
  server lacks `_embed_items`/`_score_documents`, so these error out against it —
  confirming they bind to the new seam.)
- `tests/unit/test_dependency_drift.py` — **P7.3 venv-vs-lock drift gate**
  (`uv sync --all-extras --frozen --check` == 0) + P7.4 no-cap-without-a-receipt.
- `scripts/check_updates.py::check_python_deps` — venv/lock drift (security-flagged)
  + watched-package lock-vs-PyPI currency. Weekly launchd job picks it up.
- Full unit suite: **1136 pass / 5 skip** pre-P6; green after every commit's hook.

## P8 — live acceptance + the two measurements

Corpus (5 PDFs): 3 synthetic (`tests/fixtures/p8_corpus/build.py` — diagram
content only in a page-2 image, never in the prose) + NIST SP 800-82r3
architecture slice (23 pp, real figures) + NERC CIP-005-7. Ingested via the real
`rag_multimodal` routes against a live `:8942`. Full data:
`reports/runtime/p8_measurements.json`.

**Ingest:** 5 files → 100 text chunks + 46 page images in **99 s**; server RSS
3.1 GB idle → 6.2 GB after ingest. (Required a fix: `rag_mcp._read_file` had no
working PDF-text backend host-native — `docling`/`pypdf` are Docker-only — so a
`pymupdf` fallback was added; without it the text side of RRF is dead on the
host. Pre-existing, not a sync casualty.)

**Acceptance — 3 of 5:**

| check | result |
|---|---|
| prose-only query → `kind:"text"` hit from the right file | **pass** |
| result set is mixed text+visual (RRF fusion alive) | **pass** |
| `kb_search_all` carries `kb_id` | **pass** |
| diagram-only query → that visual page at **rank 1** | **fail** — the visual page *is* retrieved (rank 2, correct `page`/`kind`), but a semantically-adjacent page-1 **text** chunk from the same PDF wins the final RRF tiebreak (`1/(60+1)` vs `1/(60+1)`) |
| ditto for the ESP zone diagram | **fail** — same shape; a CIP-005-7 prose chunk ranks 1 |

The retrieval and labelling work; the **RRF text-vs-visual weighting** needs
tuning (a modest visual boost, or more coarse-visual depth before rerank) for
diagram-only queries to top the list. Out of scope for landing the runtime;
recorded as a follow-up.

**Measurement 1 — `max_pixels`:** diagram-page **recall@5 = 1.0 at both** the
default cap (1.84 M px) and a raised cap (2.66 M px); the page is always in the
top 5. `_render_pages` at 150 DPI (~2.10 M px US-Letter) is still above the
default cap so pages *are* downscaled — but the effect is not visible at this
corpus size (5 docs) without small-text queries against a much larger set.
**Verdict: no measurable diagram-recall change here.** The coherent fix (render
DPI and cap set together) is still worth doing; P8 could not demonstrate the
payoff at this scale.

**Measurement 2 — `VL_RERANK_CHUNK` (2 / 4 / 8 / 16):** `kb_search` latency is
**flat at ~52 s** across every chunk size — the cost is query embed + visual
coarse search + reranking ~15 page images through the 2B VLM, not chunk
batching. Server RSS was noisy and did **not** show a memory-pressure cliff up
to chunk 16 (9.2 / 9.9 / 6.6 / 4.8 GB — inversely correlated, i.e. measurement
noise / GC timing between restarts, not signal). **Default 4 stands** — safe,
and no benefit shown from raising it. The ~52 s/query visual-rerank cost is the
real performance characteristic to note.

## Gate count

`python3 scripts/validate_system.py` registry unchanged by this task (no new
lettered check added — the drift gate lives in the pytest unit suite, which the
`validate-system` pre-push hook also runs). New pytest gates: 2 files, 10 tests.

## Still open

- **RRF text-vs-visual weighting** — a diagram-only query retrieves the right
  visual page but a semantically-adjacent text chunk from the same file wins the
  final tiebreak. Needs a visual RRF boost or more coarse-visual depth. (P8)
- **Render DPI vs `max_pixels`** — `_render_pages` renders above the default
  cap; set both coherently. P8 couldn't show the payoff at 5 docs; revisit on a
  real KB.
- **`kb_search` latency ~52 s** when the visual side has ~15 candidates
  (2B-VLM rerank). Acceptable for a KB tool; noted.
- `:8918` / `:8924` restarted onto the new venv during P5 but are `nohup`
  processes, not launchd-supervised (pre-existing; noted, not fixed).
- Higgs / Qwen3-TTS functional synth (imports + models OK; not run).
