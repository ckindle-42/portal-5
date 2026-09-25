---
id: unit-surface-archive-engine-h2h
kind: mixed
title: "Engine head-to-head and Bonsai probe tooling \u2014 archival record"
sources:
- type: code
  path: scripts/_archive/engine_h2h_20260924/**/*.py
claims: []
confidence: high
tags:
- authored-v1
- archive
- bench
created_at: 1790305358.8005278
updated_at: 1790305358.8005278
---

The September 2026 engine head-to-head (Ollama, oMLX, mlx-serve, Rapid-MLX,
vllm-mlx, mlx_lm.server, MTPLX, PrismML llama.cpp and MLX forks) and the Bonsai
compression probe ran on this harness, its registry, the PrismML MLX adapter,
its fixtures, WFE engine-mode plans and a thinking-on deep-lane runner. All of
it is archived under `scripts/_archive/engine_h2h_20260924/`, with a README
covering the verdicts, what was removed from the host, and how to revive it.
Result receipts stay live in `tests/benchmarks/results/engine_h2h/`.

## Why

No test engine earned a place beside Ollama and oMLX, and Bonsai's compression
held on speed and synthetic quality but not in agentic use. The engines and
models were removed and the tooling was archived rather than deleted, so its
parts (single-flight lock, swap guard, cold-prefill method, per-engine
think-off dialects, template diffing) can be reused without rebuilding them.
