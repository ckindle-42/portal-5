---
id: unit-known-limitations-ollama-native-mlx-engine-evaluation-findings-2026-07-01
kind: what
title: "KNOWN_LIMITATIONS \u2014 Ollama Native MLX Engine \u2014 Evaluation Findings\
  \ (2026-07-01)"
sources:
- type: code
  path: tests/benchmarks/bench_mlx_hf.py
- type: code
  path: config/backends.yaml
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/README.md
last_generated_commit: 5d5f217e3cd2b239cd1a8444769243ea0a3f752e
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6687732
updated_at: 1784946220.6687732
---

Ollama 0.31.1 added a built-in MLX engine (distinct from the retired standalone `mlx_lm` proxy) that claims a large MTP-driven speedup for Gemma 4. A same-day evaluation of that engine, plus a broader catalog sweep for MLX equivalents of the fleet, is documented in `coding_task/TASK_EVAL_GEMMA4_MLX_TAGS_V1.md`. The sweep tooling is `tests/benchmarks/bench_mlx_hf.py`, which pulls any HF `mlx-community` repo and benches it directly via `mlx_lm` — a throwaway measurement tool, not a serving mechanism, and its module docstring explicitly forbids wiring it into launch hooks or the pipeline. **No production config was changed**: `config/backends.yaml` was reverted, the pulled MLX models were deleted, and disk usage was restored to its pre-evaluation baseline.

## Why

Ollama's claimed MLX speedups are real enough to measure but unusable in production because the pipeline only talks to Ollama's GGUF-serving endpoint, so the evaluation had to be recorded without leaving artifacts behind. Keeping the throwaway bench tool separate from the serving stack, and reverting config after measuring, prevents an experiment from silently becoming an undocumented production dependency.
