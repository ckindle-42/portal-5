---
id: unit-archive-mlx-laguna-model
kind: mixed
title: "Laguna MLX model \u2014 archived custom-architecture candidate"
sources:
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/mlx-model-laguna.py
  commit: 2d2e9c0f
last_generated_commit: 2d2e9c0f
claims: []
confidence: high
tags:
- authored-v1
- archive
- mlx
created_at: 1785797132.539455
updated_at: 1785797132.539455
---

This file is the Laguna (Poolside AI) model implementation for mlx-lm,
archived with the rest of the retired MLX inference stack. It is a
256-expert MoE architecture with mixed full/sliding-window attention,
per-layer head counts, per-head gating, and YaRN RoPE for the full layers.

## Why

The archive exists to record what was tried and retired at `3a0c58e`, when
the MLX inference proxy was replaced by Ollama's native MLX Metal backend.
Laguna was a candidate coding model whose custom architecture required a
patched mlx-lm; once Ollama served the coding tier with equivalent or better
throughput, maintaining a forked model file was a cost without a user. The
file's *why* is therefore not what it does but the decision it documents:
a dual-stack inference arrangement was deliberately collapsed to one tier.

## Interfaces

The module defines the model classes and args consumed by mlx-lm, importing
`BaseModelArgs` and attention primitives from the sibling `base` module. It
has no callers in the live tree.

## Gotchas

This is dead code by design — do not re-add the MLX proxy stack to serve
it. The Ollama backend is the single inference tier per the architecture
decision.
