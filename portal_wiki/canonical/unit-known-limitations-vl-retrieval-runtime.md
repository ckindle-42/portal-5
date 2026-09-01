---
id: unit-known-limitations-vl-retrieval-runtime
kind: what
title: Qwen3-VL Retrieval Runtime — Landed, With a Verbatim-Error Lesson
sources:
- type: code
  path: scripts/vl-retrieval-server.py
- type: code
  path: pyproject.toml
- type: code
  path: scripts/embedding-launchd-wrapper.sh
claims: []
confidence: high
tags:
- rag
- known-limitations
- runtime
- verified-v1
---

- **ID**: P5-VL-RUNTIME-001
- **Status**: RESOLVED — `TASK_VL_RUNTIME_LANDING_V4`. The VL retrieval server
  (`:8942`) loads `mlx-community/Qwen3-VL-Embedding-2B-mxfp8` (embed, dim 2048,
  `normalize=True`) and `-Reranker-2B-mxfp8` (rerank, `(N,)` scores);
  `/ready` returns `ready: true`, `/health` is non-empty.
- **The real cause (three snapshots, one symptom)**: the T9 record carried
  `'NoneType' object has no attribute 'model_type'` for five months; V3's read
  of the 0.0.5 source predicted `ValueError: Model type qwen3_vl not supported`;
  the live host actually raised
  `ImportError: AutoImageProcessor requires the Torchvision library…`. Each was
  correct for a *different environment snapshot* and each pointed at a different
  fix ("defer to a runtime re-eval", "upgrade the package", "add a missing
  dependency"). The block was **not** "the architecture is unsupported" —
  `mlx-embeddings 0.1.0` already shipped the `qwen3_vl` module. It was:
  1. **`torchvision` was absent** from `pyproject.toml`, `uv.lock`, and every
     venv. transformers 5.x gates `AutoImageProcessor` behind
     `@requires(backends=("vision",))` where `vision` == torchvision, and the
     Qwen3-VL processor constructs it. Preprocessing runs on the PIL path
     (`Qwen2VLImageProcessorPil`), so the torchvision *version* is inert to
     output — it only needs to import. Pinned `torchvision==0.28.0`
     (`requires torch==2.13.0`, the live torch).
  2. The runtime existed **only as unpinned, hand-patched venv state**; the lock
     still resolved `mlx-embeddings 0.0.5`. A routine `uv sync` — a fresh clone,
     a normal `launch.sh` path, or the pre-commit hook's own `uv run pytest` —
     would have reverted it. Fixed: the lock was reconciled *to* the venv, and
     `embedding-launchd-wrapper.sh` now runs `uv run --no-sync` behind a
     `uv sync --frozen --check` pre-flight that fails loudly on drift.
     `TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2` D1 factored that pre-flight
     into `scripts/lib/venv_preflight.sh` (`_venv_lock_preflight`, now
     direction-aware — it distinguishes "venv ahead of lock" from "venv behind"
     and only recommends `uv sync` for the latter) and applied it to every
     service that shares the fragile MLX runtime: `:8917`, `:8918` (mlx-speech),
     `:8924` (mlx-transcribe), `:8942` (VL). The pure-Python MCP services
     (`mitre`/`compliance`/`data`/`wiki`/…) that also resolve from `.venv` are
     **deliberately not gated** — they carry no MLX/torch dependency, and a hard
     drift-fail under launchd `KeepAlive` would crash-loop the whole fleet on an
     unrelated dependency bump.
  3. The old server's rerank seam called the embedding `/embed`. The rewrite
     uses `model.process({"query":…, "documents":[…]})`.
- **Video is unsupported** on this runtime
  (`_UnsupportedVideoProcessor.__call__` raises) — do not inherit the model
  card's video claim.
- **Two library quirks the server works around**: `mlx_embeddings.load()` fetches
  a restrictive `allow_patterns` set that omits `chat_template.jinja` (→ "this
  processor does not have a chat template"), so the server does a full
  `snapshot_download` first; and `compute_qwen3_vl_hidden_states` only clears
  `language_model._position_ids` on calls with pixel_values, so two text-only
  `process()` calls of different sequence length crash with "Too many indices
  for array with 2 dimensions" — the server clears that state before every call.

## Why

The generalisable lesson: **in an environment that drifts silently, a
paraphrased error string is worse than no error string** — it fossilises a
diagnosis of a runtime that no longer exists, and every reader downstream
inherits the wrong remedy. Every phase of the landing captured the **verbatim
traceback together with the resolved dependency versions that produced it**
(`reports/runtime/`). Record both, always, together.
