---
id: unit-p5-roadmap-p5-fut-009-model-size-aware-admission-control-mlx-proxy
kind: what
title: "P5_ROADMAP \u2014 P5-FUT-009: Model-Size-Aware Admission Control (MLX Proxy)"
sources:
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/README.md
- type: code
  path: .env.example
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: portal/platform/inference/load_guard.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5915961
updated_at: 1784946220.5915961
---

P5-FUT-009 shipped in the retired MLX proxy and is now historical. The archived
`scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py` holds the implementation:
`MODEL_MEMORY` maps model ids to estimated GB (loaded from the `mlx_models`
`memory_gb` metadata in `config/backends.yaml`), and `_check_memory_for_model()`
runs before any model switch, rejecting a load with an HTTP 503 and an
operator-actionable message when required GB plus `MEMORY_HEADROOM_GB` exceeds
free memory. The override env vars were `MLX_MEMORY_HEADROOM_GB` (default 10.0)
and `MLX_MEMORY_UNKNOWN_DEFAULT_GB` (default 20.0). The proxy and its unit tests
were deleted at commit 75c24a9, which retired
the whole MLX inference tier; the archive README at
`scripts/_archive/mlx-retired-3a0c58e/` documents recovering the tests
via git. Memory pressure is now managed by Ollama itself through
`OLLAMA_MAX_LOADED_MODELS` and `OLLAMA_MEMORY_LIMIT` in `.env.example` and
`deploy/portal-5/docker-compose.yml`.

## Why

The admission-control code survives only as reference, but the reason it existed
has not gone away: on a fixed-memory Mac, a model-switch pre-flight check was the
difference between a clean swap and an OOM crash. Retiring the proxy moved that
niche to Ollama's native `OLLAMA_MAX_LOADED_MODELS` cap, while the archived
implementation remains the documented pattern if a successor engine ever needs a
memory gate again.

## Successor: the cold-load guard (2026-10-07)

Ollama's cap proved insufficient once oMLX shared the same unified memory. On
2026-10-07 Ollama started a 22.7 GiB load with 10 GiB system-free while oMLX loaded a
27B model. Swap ran out, jetsam could not recover, and the hardware watchdog reset
the Mac. The pipeline's `MEMORY_GATE_PCT` gate could not fire: it reads `vm_stat`,
which the pipeline container lacks. `portal/platform/inference/load_guard.py`, wired
into the Ollama native transport, is the successor. Before a request reaches Ollama
for a model that is not resident, it serialises cold loads host-wide and waits while
oMLX is mid-load. If the model (weights × 1.25 + 2 GiB) does not fit in oMLX's
`final_ceiling` minus its resident memory plus what Ollama can evict, and oMLX has no
active or waiting request, it unloads oMLX's idle unpinned models (least recently used
first) through the admin API and measures again. If the model still does not fit, it
refuses with HTTP 507. The refusal cascades like an oMLX capacity rejection. Resident models (the
router, `task-router`, warm seats) are never delayed. Readings the compliance module
sends straight to Ollama's `/api/chat` do not pass through the pipeline, so the guard
does not cover them.
