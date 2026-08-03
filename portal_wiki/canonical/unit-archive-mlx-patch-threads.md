---
id: unit-archive-mlx-patch-threads
kind: mixed
title: "MLX thread patch \u2014 archived dependency-upgrade burden"
sources:
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/patch-mlx-threads.py
  commit: 2d2e9c0f
last_generated_commit: 2d2e9c0f
claims: []
confidence: high
tags:
- authored-v1
- archive
- mlx
created_at: 1785797160.858874
updated_at: 1785797160.858874
---

This is the MLX thread-patch script, archived with the retired MLX stack:
it patched mlx_lm after installation to fix cross-thread stream usage (mlx
0.31.2 made GPU streams strictly thread-local) and installed the Laguna
architecture plugins that were not yet upstreamed.

## Why

The patch was the maintenance cost that helped sink the MLX inference tier:
mlx 0.31.2's thread-local stream change broke generation running on a worker
thread (a stream created on the main thread was unusable there), and every
mlx upgrade risked re-breaking the patch. This recurring maintenance burden,
plus the admission-control complexity of the proxy, is precisely what the
retirement decision at `3a0c58e` weighed — Ollama absorbed the model serving
and the patch disappeared. The archive records why the dual-stack was
untenable: it required patching a third-party dependency on every upgrade.

## Interfaces

The script patched the installed mlx_lm package and added the Laguna
plugins. No live callers remain.

## Gotchas

The thread-local-stream bug is a dependency-upgrade failure mode: any stack
that pins a version-specific patch to mlx_lm would face the same recurring
maintenance on every upgrade.
