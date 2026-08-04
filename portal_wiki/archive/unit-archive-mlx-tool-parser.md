---
id: unit-archive-mlx-tool-parser
kind: mixed
title: "Laguna MLX tool parser \u2014 archived custom tool-call format"
sources:
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/mlx-tool-parser-laguna.py
  commit: 2d2e9c0f
last_generated_commit: 2d2e9c0f
claims: []
confidence: high
tags:
- authored-v1
- archive
- mlx
created_at: 1785797150.898161
updated_at: 1785797150.898161
---

This file is the Laguna tool-call parser for mlx-lm, archived with the
retired MLX stack: it parses Laguna's JSON tool calls, which are wrapped in
`<tool_call>...</tool_call>` tags.

## Why

The parser existed because Laguna's tool-call format differed from the
models mlx-lm supported natively, and tool-calling support was a hard
requirement for a coding model. It retired at `3a0c58e` with the rest of the
Laguna/MLX stack — once Ollama served the coding tier, the custom parser
lost its reason to exist. The archive preserves the format knowledge (JSON
wrapped in tool_call tags) in case a future model uses the same convention.

## Interfaces

The module defined the tag constants and the parse logic consumed by
mlx-lm's tool-calling path. No live callers remain.

## Gotchas

Dead by design — the custom parser applied only to the retired Laguna model
family.
