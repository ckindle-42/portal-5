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
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
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
were deleted at commit 3a0c58e, which retired
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
