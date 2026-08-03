---
id: unit-archive-mlx-switch-bench
kind: mixed
title: "MLX switch benchmark \u2014 archived proxy-vs-raw timing"
sources:
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/mlx-switch-benchmark.py
  commit: 2d2e9c0f
last_generated_commit: 2d2e9c0f
claims: []
confidence: high
tags:
- authored-v1
- archive
- mlx
created_at: 1785797145.0569332
updated_at: 1785797145.0569332
---

This is the MLX model-switch benchmark, archived with the retired MLX stack:
it timed server start/stop in three modes (raw direct server, through the
proxy, and both for comparison) so the proxy's switch cost could be measured
against raw mlx_lm/mlx_vlm startup.

## Why

The benchmark existed to answer a cost question the proxy design depended on:
is the proxy's model switching overhead worth it versus raw server starts?
It retired with the stack at `3a0c58e` because the proxy it measured is gone
and Ollama manages model residency itself. Its *why* is the record that the
switch-cost measurement was made, the number informed the retirement
decision, and the tool that made it is preserved rather than deleted so the
reasoning stays auditable.

## Interfaces

The script ran in `raw`/`proxy`/`both` modes with `--dry-run` to show the
plan without executing. No live callers remain.

## Gotchas

The timings it produced were specific to the retired proxy arrangement and
are not comparable to Ollama's current loading behaviour.
