---
id: unit-surface-archive-mlx
kind: mixed
title: "Retired MLX inference tier \u2014 archival record of the dual-stack abandonment"
sources:
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/*.py
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- authored-v1
- archive
- mlx
created_at: 1785887000.0
updated_at: 1785887000.0
---

Portal 5 ran a dual-stack inference arrangement until commit `3a0c58e`,
when the MLX tier was retired for a single Ollama tier. It spanned a
model-aware proxy switching between `mlx_lm` and `mlx_vlm`, a custom
Laguna model with a bespoke tool parser, patched mlx internals, plus
readiness, watchdog, smoke-test, and switch-cost tooling. This surface
unit is that archival contract.

## Why

Collapsing to one tier was deliberate: Ollama's native MLX Metal backend
reached parity on this hardware, so the proxy's admission-control
complexity, switch latency near thirty seconds, and the cost of patching
a third-party dependency on every mlx upgrade became overhead with no
user. Two fragile couplings — a forked model file and a
thread-local-stream patch — disappeared with it. The archive keeps the
reasoning auditable.

## Interfaces

At the surface the tier exposed an auto-switching endpoint on port 8081,
spawning text and vision servers on 18081 and 18082. A readiness
watcher polled the health route and wrote a state file under `/tmp` so
consumers shared one source of truth. Nothing in the live tree imports
the archived scripts.

## Gotchas

Thread-local GPU streams in mlx 0.31.2 broke generation on worker
threads — a version-specific patch re-pays its maintenance on every
upgrade. A missing `chat_template` key in `tokenizer_config.json`
silently disabled tool calling; check the missing key first.
Supervision must be external, readiness decoupled into one shared state
file, and empty content gated before benching. MLX remains for speech,
transcription, embeddings, and reranking — never chat inference.
