---
id: unit-MLX_CHANGES_2026-04-26-3-homebrew-mlx-0-31-2-python-bindings-incomplete
kind: why
title: "MLX_CHANGES_2026-04-26 \u2014 3. Homebrew mlx 0.31.2 Python Bindings Incomplete"
sources:
- type: design
  path: docs/MLX_CHANGES_2026-04-26.md
  section: 3. Homebrew mlx 0.31.2 Python Bindings Incomplete
last_generated_commit: ''
confidence: high
tags:
- docs
- MLX_CHANGES_2026-04-26
created_at: 1783195000.87664
updated_at: 1783195000.87664
---

- **Severity**: High — `import mlx.core` fails after `brew upgrade mlx`
- **Symptom**: `ModuleNotFoundError: No module named 'mlx.core'` after upgrading mlx via Homebrew.
- **Root cause**: Homebrew formula links `.so` files via symlinks that break on Python 3.14. The Cellar has `core.cpython-314-darwin.so` and full `nn/` package, but site-packages only gets partial copies.
- **Fix applied**: Manual copy of missing files:
  ```
  cp /opt/homebrew/Cellar/mlx/0.31.2/lib/python3.14/site-packages/mlx/core.cpython-314-darwin.so /opt/homebrew/lib/python3.14/site-packages/mlx/
  cp -r /opt/homebrew/Cellar/mlx/0.31.2/lib/python3.14/site-packages/mlx/nn/ /opt/homebrew/lib/python3.14/site-packages/mlx/nn/
  cp -r /opt/homebrew/Cellar/mlx/0.31.2/lib/python3.14/site-packages/mlx/optimizers/ /opt/homebrew/lib/python3.14/site-packages/mlx/optimizers/
  cp -r /opt/homebrew/Cellar/mlx/0.31.2/lib/python3.14/site-packages/mlx/_distributed_utils/ /opt/homebrew/lib/python3.14/site-packages/mlx/_distributed_utils/
  ```
- **Status**: Fixed manually. Will break again on next `brew upgrade mlx`. Need a post-install script or use `pip install mlx` instead of Homebrew.
