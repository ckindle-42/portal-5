---
id: unit-known-limitations-p5-mlx-eval-001-gguf-fleet-regressed-slightly-on-0-31-1-mtp-is-mlx-engine-only
kind: what
title: "KNOWN_LIMITATIONS \u2014 P5-MLX-EVAL-001 \u2014 GGUF fleet regressed slightly\
  \ on 0.31.1; MTP is MLX-engine-only"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: tests/benchmarks/bench_mlx_hf.py
last_generated_commit: 50b73876729db7181402fcbcc48400caa1ba1e40
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.669174
updated_at: 1784946220.669174
---

- **Description**: Ollama 0.31.1's claimed MTP speedup applies only when Ollama selects its own MLX engine subprocess (triggered by official `-mlx`-tagged models), so the GGUF fleet routed through `llama-server` regardless of version. Separately, the GGUF fleet measured slower after the 0.31.1 upgrade, and the 5-11% regression is recorded in `coding_task/TASK_SEC_DRIFT_GATE_V1.md` as the motivating example for the delta gate it adds — a version-induced performance shift that absolute gates would not flag. The MTP claim and its MLX-engine-only scope are documented in `coding_task/TASK_EVAL_GEMMA4_MLX_TAGS_V1.md`.
- **Impact**: None today (no config changed). Documented so a future Ollama upgrade isn't mistaken for a routing/pipeline regression.

## Why

An Ollama point release silently shifting GGUF throughput is exactly the failure a routing regression gate cannot see, because routing behavior is unchanged while latency moves. Recording the measured regression and the scope of the MTP claim keeps the two facts distinct — the speedup is an MLX-engine property, the slowdown is a llama.cpp-version property — so a future upgrade is evaluated against the right baseline.
