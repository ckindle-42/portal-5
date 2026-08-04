---
id: unit-MLX_CHANGES_2026-04-26-2-mlx-lm-0-31-2-server-puts-content-in-reasoning-f
kind: why
title: "MLX_CHANGES_2026-04-26 \u2014 2. mlx-lm 0.31.2 Server Puts Content in `reasoning`\
  \ Field"
sources:
- type: design
  path: docs/MLX_CHANGES_2026-04-26.md
  section: 2. mlx-lm 0.31.2 Server Puts Content in `reasoning` Field
last_generated_commit: ''
confidence: high
tags:
- docs
- MLX_CHANGES_2026-04-26
created_at: 1783195000.876099
updated_at: 1783195000.876099
---

- **Severity**: High — breaks content display in Open WebUI for all models
- **Symptom**: `mlx_lm.generate` CLI returns content correctly, but `mlx_lm.server` HTTP endpoint returns content in `message.reasoning` instead of `message.content`. Also affects SSE streaming: `delta.reasoning` instead of `delta.content`.
- **Root cause**: mlx_lm 0.31.2 server treats all models as reasoning models when emitting responses.
- **Fix applied**: Pipeline now promotes `reasoning` → `content` in both:
  - Non-streaming path: `router_pipe.py:2042` (already existed, verified working)
  - Streaming path: `router_pipe.py:3127` (newly added for MLX SSE pass-through)
- **Status**: Fixed in pipeline. Upstream mlx_lm server bug — report to ml-explore/mlx-lm.
