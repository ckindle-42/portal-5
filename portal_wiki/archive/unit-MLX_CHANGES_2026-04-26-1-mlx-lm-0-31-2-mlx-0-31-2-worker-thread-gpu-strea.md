---
id: unit-MLX_CHANGES_2026-04-26-1-mlx-lm-0-31-2-mlx-0-31-2-worker-thread-gpu-strea
kind: why
title: "MLX_CHANGES_2026-04-26 \u2014 1. mlx-lm 0.31.2 + mlx 0.31.2: Worker Thread\
  \ GPU Stream Crash (FIXED)"
sources:
- type: design
  path: docs/MLX_CHANGES_2026-04-26.md
  section: '1. mlx-lm 0.31.2 + mlx 0.31.2: Worker Thread GPU Stream Crash (FIXED)'
last_generated_commit: ''
confidence: high
tags:
- docs
- MLX_CHANGES_2026-04-26
created_at: 1783195000.8758101
updated_at: 1783195000.8758101
---

- **Severity**: Critical — all completions hang/crash, UAT produces 0 results
- **Symptom**: `mlx_lm.server` starts and reports `/health` OK but every POST to `/v1/chat/completions` causes `RuntimeError: There is no Stream(gpu, 0) in current thread.` in `Thread-2 (_generate)`. The server returns HTTP 200 but with no body (streaming hangs, non-streaming times out).
- **Root cause**: mlx 0.31.2 made GPU streams strictly thread-local. `mlx_lm/generate.py` creates `generation_stream = mx.new_stream(mx.default_device())` at module-import time in the main thread. When the `_generate` worker thread calls `with mx.stream(generation_stream):`, mlx cannot find Stream(gpu, 0) in the worker thread's context.
- **Fix applied**: Patched `/opt/homebrew/lib/python3.14/site-packages/mlx_lm/generate.py` line 226:
  - Before: `generation_stream = mx.new_stream(mx.default_device())`
  - After: `generation_stream = mx.new_thread_local_stream(mx.default_device())`
  - `ThreadLocalStream` is resolved per-thread at use time — it works in any worker thread without per-thread initialization.
- **Re-apply script**: `python3 scripts/patch-mlx-threads.py` (idempotent, re-run after any mlx_lm upgrade).
- **Status**: Fixed. Upstream mlx_lm bug — report to ml-explore/mlx-lm.
