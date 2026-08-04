---
id: unit-archive-mlx-smoke-test
kind: mixed
title: "MLX smoke test \u2014 archived empty-content gate"
sources:
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/smoke_test_mlx.py
  commit: 2d2e9c0f
last_generated_commit: 2d2e9c0f
claims: []
confidence: high
tags:
- authored-v1
- archive
- mlx
created_at: 1785797164.1964521
updated_at: 1785797164.1964521
---

This is the V5 Apple Metal smoke test, archived with the retired MLX stack:
it ran 50-token greedy generation per model to detect empty-content defects
and runtime failures, and its JSON results gated which models proceeded to
the Phase E bench (failed models were skipped to avoid wasting bench time).

## Why

The smoke test encoded the honest-bench principle that a model that cannot
generate is not worth benching: running a full TPS bench on a model that
returns empty content wastes hours and corrupts the aggregate numbers. The
empty-content gate (models that produce nothing are skipped) is the durable
lesson. It retired at `3a0c58e` with the MLX stack it tested, but the
gate-before-bench pattern survives in the current bench flow.

## Interfaces

The script ran each candidate through 50-token greedy generation, checked
for empty output, and wrote JSON results. No live callers remain.

## Gotchas

The empty-content defect it guarded against was a real P5-MLX-006/008-class
failure — the check that catches a model generating nothing before hours of
bench time is spent is the value the archive preserves.
