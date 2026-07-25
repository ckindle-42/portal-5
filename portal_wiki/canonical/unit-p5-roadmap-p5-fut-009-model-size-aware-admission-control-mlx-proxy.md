---
id: unit-p5-roadmap-p5-fut-009-model-size-aware-admission-control-mlx-proxy
kind: what
title: "P5_ROADMAP \u2014 P5-FUT-009: Model-Size-Aware Admission Control (MLX Proxy)"
sources:
- type: doc
  path: P5_ROADMAP.md
  commit: 05e42ec2
  section: 'P5-FUT-009: Model-Size-Aware Admission Control (MLX Proxy)'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5915961
updated_at: 1784946220.5915961
---

IMPLEMENTED in v6.0.0 (`scripts/mlx-proxy.py`). Note: the MLX proxy was subsequently retired
at commit 3a0c58e — this note is historical. Ollama's native model-load behavior now handles
memory pressure via OLLAMA_MAX_LOADED_MODELS and OLLAMA_MEMORY_LIMIT (see Admin Guide).

**What was built:**
- `MODEL_MEMORY` dict: 16 model tags → estimated GB (sourced from CLAUDE.md catalog)
- `_check_memory_for_model()`: pre-flight check in `ensure_server()` before any model switch
- Rejects with HTTP 503 + actionable message (e.g. "Model needs ~46GB, only 30GB free — stop ComfyUI or unload Ollama first")
- `MEMORY_HEADROOM_GB` env var replaces the hardcoded 10GB floor
- `MLX_MEMORY_UNKNOWN_DEFAULT_GB` env var controls the assumed size for unrecognized models
- 9 unit tests in `tests/unit/test_mlx_proxy.py` (mocked memory reads)

**Configuration (`.env`):**
```
MLX_MEMORY_HEADROOM_GB=10
MLX_MEMORY_UNKNOWN_DEFAULT_GB=20
```

---
