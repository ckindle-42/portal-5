---
id: unit-MLX_CHANGES_2026-04-26-upgrades-applied
historical: true
kind: why
title: "MLX_CHANGES_2026-04-26 \u2014 Upgrades Applied"
sources:
- type: design
  path: docs/MLX_CHANGES_2026-04-26.md
  section: Upgrades Applied
confidence: high
tags:
- docs
- MLX_CHANGES_2026-04-26

---


| Package | Old | New | Notes |
|---------|-----|-----|-------|
| mlx (core) | 0.31.1 | 0.31.2 | Homebrew upgrade; Python bindings required manual copy of `core.cpython-314-darwin.so` and `nn/` modules from Cellar |
| mlx-lm | 0.31.1 | 0.31.2 | Adds gemma4 architecture support, Gemma4 KV-shared layer fixes, tool parser fixes |
| mlx-vlm | 0.4.4 | 0.4.4 | Latest; compatible with mlx 0.31.2 after core fix |
