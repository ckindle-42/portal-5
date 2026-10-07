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

## Successor: the load guard (2026-10-07)

Ollama's cap proved insufficient once oMLX shared the same unified memory. On
2026-10-07 Ollama started a 22.7 GiB load with 10 GiB system-free while oMLX loaded a
27B model. Swap ran out, jetsam could not recover, and the hardware watchdog reset
the Mac. The pipeline's `MEMORY_GATE_PCT` gate could not fire: it reads `vm_stat`,
which the pipeline container lacks.

`portal/platform/inference/load_guard.py` is the successor. It sits in the pipeline's
engine transport, which every chat request to Ollama or oMLX passes through.

- **Busy tracking.** It counts in-flight requests per (engine, model). Only idle
  models count as evictable on Ollama or freeable on oMLX, so concurrent multi-model
  work never admits a load that fits only by evicting a sibling's model.
- **Load-scoped serialisation.** Cold loads on both engines take one host-wide lock,
  held until the model is resident rather than for the whole answer. Seats load in
  turn and then generate concurrently, and the two engines can no longer measure the
  same free memory at once.
- **Queue, then refuse.** An Ollama cold load that does not fit frees idle oMLX
  models (least recently used first, through oMLX's admin API) and waits for
  in-flight work to drain, without holding the lock. It is refused with HTTP 507 only
  when the caller's `X-Portal-Load-Wait` runs out (default `LOAD_GUARD_WAIT_S`;
  compliance sends `COMPLIANCE_LOAD_WAIT_S`). The router cascades the 507 as a
  capacity rejection.
- **Plans.** `POST /admin/load-plan` says whether a model set fits together now, so
  batch work can run in fit-sized waves.

Footprint is weights × 1.25 + 2 GiB, raised to the size observed the last time the
model was resident. Headroom is oMLX's `final_ceiling` minus its resident memory, plus
idle Ollama residents. Verified live: two cold Ollama seats loaded in turn and
generated concurrently; two cold oMLX seats were serialised; an oMLX cold load
followed by an Ollama cold load was serialised across engines; no refusals, and swap
stayed above the watchdog floor. Resident models (the router, `task-router`) are
never delayed. Calls that reach Ollama without the pipeline are not covered:
`TASK_HOST_MEMORY_SAFETY_V1` W2 routes them through it.
