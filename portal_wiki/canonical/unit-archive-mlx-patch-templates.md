---
id: unit-archive-mlx-patch-templates
kind: mixed
title: "MLX template patcher \u2014 archived tokenizer packaging fix"
sources:
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/patch-mlx-templates.py
  commit: 2d2e9c0f
last_generated_commit: 2d2e9c0f
claims: []
confidence: high
tags:
- authored-v1
- archive
- mlx
created_at: 1785797157.54627
updated_at: 1785797157.54627
---

This is the MLX chat-template patcher, archived with the retired MLX stack:
it embedded `chat_template.jinja` into `tokenizer_config.json` for MLX models
that shipped the template as a separate file, because mlx_lm loads the
template from `tokenizer_config.json["chat_template"]` and a missing key
silently disabled tool calling.

## Why

The patch existed because a subtle packaging gap in many MLX quantizations
produced a silent capability failure: the template file was present but the
config key was missing, so the tokenizer reported no tool-calling support
and models lost tool use without any error. The patcher made the dependency
explicit by embedding the template. It retired at `3a0c58e` with the MLX
stack, and the archive preserves the failure mode — a missing config key
silently disabling a capability — as a warning pattern for any future
tokenizer packaging.

## Interfaces

The script rewrote `tokenizer_config.json` to include the embedded template.
No live callers remain.

## Gotchas

The silent-disable failure mode is the reason the patch existed at all —
if this pattern reappears in another stack, the missing key is the thing to
check first.
