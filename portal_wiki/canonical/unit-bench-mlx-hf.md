---
id: unit-bench-mlx-hf
kind: mixed
title: "Bench mlx-hf \u2014 HF safetensors staging for comparison"
sources:
- type: code
  path: tests/benchmarks/bench_mlx_hf.py
  commit: f09fdb85
last_generated_commit: f09fdb85
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798600.97055
updated_at: 1785798600.97055
---

`bench_mlx_hf.py` pulls a HuggingFace mlx-community safetensors repository
for one-off comparison benching, using the same snapshot-download mechanism
launch.sh used before the MLX retirement.

## Why

Ollama's `hf.co` puller only accepts GGUF repositories — it cannot pull
mlx-community safetensors repos, even though Ollama has its own separate,
narrower set of official `-mlx` library tags. The script fills that gap for
the comparison-bench use case where an operator wants to measure an
mlx-community model against the fleet. It exists *despite* the single-tier
decision because it is a measurement tool, not an inference path: MLX is no
longer a serving tier, but comparing a candidate still needs the ability to
stage an mlx repo.

## Interfaces

The script downloads the HF repo and stages it for the one-off comparison.

## Gotchas

This is explicitly a one-off comparison tool, not a serving path — the
staged model is for benching, and the single-tier rule still applies to what
serves traffic.
