---
id: unit-MLX_CHANGES_2026-04-26-what-needs-fixing-in-portal-5
kind: why
title: "MLX_CHANGES_2026-04-26 \u2014 What Needs Fixing in Portal 5"
sources:
- type: design
  path: docs/MLX_CHANGES_2026-04-26.md
  section: What Needs Fixing in Portal 5
last_generated_commit: ''
confidence: high
tags:
- docs
- MLX_CHANGES_2026-04-26
created_at: 1783195000.877404
updated_at: 1783195000.877404
---


1. **Post-brew-upgrade script**: Add a script to `/scripts/` that copies missing mlx Python bindings after Homebrew upgrades.
2. **Spec-decoding re-enable**: Monitor mlx_lm releases; re-enable `draft_models` when ArraysCache fix lands.
3. **Streaming reasoning→content**: The new code at `router_pipe.py:3127` is a hotfix. Clean up when mlx_lm server is fixed upstream.
4. ~~**Thread stream crash**~~: Fixed via `scripts/patch-mlx-threads.py` (Issue #1 above).
