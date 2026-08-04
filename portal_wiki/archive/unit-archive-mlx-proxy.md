---
id: unit-archive-mlx-proxy
kind: mixed
title: "MLX model-aware proxy \u2014 retired dual-stack coordinator"
sources:
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py
  commit: 2d2e9c0f
last_generated_commit: 2d2e9c0f
claims: []
confidence: high
tags:
- authored-v1
- archive
- mlx
created_at: 1785797138.442691
updated_at: 1785797138.442691
---

This is the MLX model-aware proxy — the retired dual-stack inference
coordinator that auto-switched between `mlx_lm.server` (text) and
`mlx_vlm.server` (vision) behind one port, keeping only one server resident
at a time under Apple Silicon's unified memory constraints.

## Why

The proxy is the centerpiece of the MLX inference tier that was retired at
`3a0c58e`. It existed because mlx-lm and mlx-vlm could not share VRAM, so a
coordinator had to load one, serve, evict, and load the other — with switch
times around thirty seconds. The retirement decision was that Ollama's
native MLX backend reached parity without the thread-patch maintenance,
admission-control complexity, and dual-stack overhead this proxy embodied.
Its *why* is the record of that trade-off: the complexity was real, it was
paid, and it was found unnecessary.

## Interfaces

The proxy exposed the auto-switching endpoint on port 8081 and spawned the
two servers on 18081/18082. It is dead code in the live tree.

## Gotchas

Do not revive the proxy. MLX is still used in the project — for speech,
transcription, embeddings, and reranking — but never for chat inference,
which is Ollama-only by rule.
