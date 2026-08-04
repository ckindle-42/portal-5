---
id: unit-MLX_CHANGES_2026-04-26-what-needs-fixing-upstream
kind: why
title: "MLX_CHANGES_2026-04-26 \u2014 What Needs Fixing Upstream"
sources:
- type: design
  path: docs/MLX_CHANGES_2026-04-26.md
  section: What Needs Fixing Upstream
last_generated_commit: ''
confidence: high
tags:
- docs
- MLX_CHANGES_2026-04-26
created_at: 1783195000.87715
updated_at: 1783195000.87715
---


1. **mlx_lm server**: Content should go in `message.content`, not `message.reasoning`, for non-reasoning models. File issue at ml-explore/mlx-lm.
2. **mlx_lm server**: `ArraysCache` needs to be trimmable or spec-decoding needs to work with non-trimmable caches. File issue at ml-explore/mlx-lm.
3. **Homebrew mlx formula**: Python bindings should be properly linked, not partially symlinked. File issue at Homebrew/homebrew-core.
