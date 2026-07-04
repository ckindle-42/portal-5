---
id: unit-MLX_CHANGES_2026-04-26-4-gemma4-architecture-requires-mlx-lm-0-31-2
kind: why
title: "MLX_CHANGES_2026-04-26 \u2014 4. gemma4 Architecture Requires mlx-lm >= 0.31.2"
sources:
- type: design
  path: docs/MLX_CHANGES_2026-04-26.md
  section: 4. gemma4 Architecture Requires mlx-lm >= 0.31.2
last_generated_commit: ''
confidence: high
tags:
- docs
- MLX_CHANGES_2026-04-26
created_at: 1783195000.876897
updated_at: 1783195000.876897
---

- **Severity**: Low — only affects `divinetribe/gemma-4-31b-it-abliterated-4bit-mlx`
- **Symptom**: `ModuleNotFoundError: No module named 'mlx_lm.models.gemma4'` on mlx-lm 0.31.1
- **Status**: Resolved by upgrading to mlx-lm 0.31.2. Model loads and generates via `mlx_lm.generate`. Server path works with content-reasoning fix (#1 above).
