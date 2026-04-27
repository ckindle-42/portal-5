#!/usr/bin/env python3
"""Patch mlx_lm after installation to fix cross-thread stream usage (mlx >= 0.31.2).

Problem (mlx 0.31.2):
  mlx 0.31.2 made GPU streams strictly thread-local. Two bugs result:

  Bug 1 — generate.py (original fix):
    `generation_stream = mx.new_stream(mx.default_device())` at module import
    time (main thread). The _generate worker thread cannot use this stream:
        RuntimeError: There is no Stream(gpu, N) in current thread.

  Bug 2 — server.py (new fix, root cause):
    ModelProvider.__init__() calls self.load() in the MAIN THREAD, placing
    model weights on Stream(gpu, 0) (main thread default). When _generate()
    worker thread tries to use the model for inference, its own stream context
    (Stream(gpu, 1+) cannot access weights from another thread's stream:
        RuntimeError: There is no Stream(gpu, 1) in current thread.
    This caused ALL mlx_lm.server inference to silently hang.

Fix 1 — generate.py:
  Change mx.new_stream() → mx.new_thread_local_stream() so the generation
  stream is resolved per-thread at use time.

Fix 2 — server.py (root cause fix):
  Remove self.load() call from ModelProvider.__init__() so the model loads
  lazily in _generate() worker thread on first request. The default_model_map
  mapping is preserved so the server still knows which model to load.

Both fixes are required together. Fix 2 alone would still fail because
generation_stream would be a cross-thread stream. Fix 1 alone would still fail
because model weights would be on the main thread's stream.

Scope: mlx_lm only. mlx_vlm uses uvicorn + asyncio (single event-loop thread)
so it does not spawn worker threads and is not affected.

Run this after any `pip install --upgrade mlx-lm` or Homebrew mlx upgrade:
    python3 scripts/patch-mlx-threads.py

The script is idempotent — safe to re-run.
"""

import re
import subprocess
import sys
from pathlib import Path


# ── Patch 1: generate.py — thread-local generation stream ────────────────────

GENERATE_OLD = "generation_stream = mx.new_stream(mx.default_device())"
GENERATE_NEW = (
    "# mlx 0.31.2+: GPU streams are thread-local. Two patches required together:\n"
    "# 1. new_thread_local_stream here — creates a per-thread stream instance so the\n"
    "#    _generate worker thread gets its own stream (not the main thread's).\n"
    "# 2. mlx_lm/server.py: ModelProvider.__init__ defers self.load() to the worker\n"
    "#    thread — ensures model weights land on the same stream as inference.\n"
    "# Without patch 2, model weights load on the main-thread stream which the worker\n"
    "# thread cannot access, causing RuntimeError on mx.eval in _serve_single/_next.\n"
    "generation_stream = mx.new_thread_local_stream(mx.default_device())"
)

# ── Patch 2: server.py — defer model loading to worker thread ─────────────────

# The block to find and replace in ModelProvider.__init__
SERVER_OLD = (
    "        # Preload the default model if it is provided\n"
    "        self.default_model_map = {}\n"
    "        if self.cli_args.model is not None:\n"
    "            self.default_model_map[self.cli_args.model] = \"default_model\"\n"
    "            self.load(self.cli_args.model, draft_model_path=\"default_model\")"
)

SERVER_NEW = (
    "        # Register the default model path but defer actual loading to the\n"
    "        # generation worker thread (_generate). mlx 0.31.2+ uses thread-local GPU\n"
    "        # streams: model weights loaded in the main thread land on a stream that\n"
    "        # the generation worker cannot access, causing RuntimeError on first eval.\n"
    "        # Loading lazily in the worker ensures all weights and cache states share\n"
    "        # the same thread-local stream context.\n"
    "        self.default_model_map = {}\n"
    "        if self.cli_args.model is not None:\n"
    "            self.default_model_map[self.cli_args.model] = \"default_model\"\n"
    "            # DO NOT call self.load() here — deferred to _generate() worker thread"
)


def find_mlx_lm_file(filename: str) -> Path | None:
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import mlx_lm; print(mlx_lm.__file__)"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        init = Path(result.stdout.strip())
        candidate = init.parent / filename
        return candidate if candidate.exists() else None
    except Exception:
        return None


def apply_patch(target: Path, old: str, new: str, name: str) -> bool:
    """Apply a string replacement patch. Returns True if patch was applied/already present."""
    text = target.read_text(encoding="utf-8")

    # Check if already patched (look for key part of new string)
    new_key = new.split("\n")[-1]  # last line of NEW (the actual code line)
    if new_key in text:
        print(f"  {name}: already patched — nothing to do.")
        return True

    if old not in text:
        # Try regex fallback for generate.py
        alt = re.search(
            r"generation_stream\s*=\s*mx\.new_stream\(mx\.default_device\(\)\)",
            text,
        )
        if alt:
            old_actual = alt.group()
        else:
            print(f"  {name}: WARNING — expected pattern not found. mlx_lm version may have changed.")
            print(f"    Expected: {repr(old[:80])}")
            return False
    else:
        old_actual = old

    patched = text.replace(old_actual, new, 1)
    if patched == text:
        print(f"  {name}: ERROR — replacement produced no change.", file=sys.stderr)
        return False

    target.write_text(patched, encoding="utf-8")
    print(f"  {name}: patch applied to {target}")
    return True


def main() -> int:
    ok = True

    # Patch 1: generate.py
    generate_py = find_mlx_lm_file("generate.py")
    if not generate_py:
        print("ERROR: could not locate mlx_lm/generate.py", file=sys.stderr)
        return 1
    print(f"Patching {generate_py}")
    if not apply_patch(generate_py, GENERATE_OLD, GENERATE_NEW, "generate.py"):
        ok = False

    # Patch 2: server.py
    server_py = find_mlx_lm_file("server.py")
    if not server_py:
        print("ERROR: could not locate mlx_lm/server.py", file=sys.stderr)
        return 1
    print(f"Patching {server_py}")
    if not apply_patch(server_py, SERVER_OLD, SERVER_NEW, "server.py"):
        ok = False

    if not ok:
        return 1

    # Sanity check: import generates cleanly
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import mlx_lm.generate; import mlx_lm.server; print('imports ok')"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print(f"Sanity check: {result.stdout.strip()}")
        else:
            print(f"WARNING: import check failed:\n{result.stderr[-500:]}")
    except Exception as e:
        print(f"WARNING: could not run sanity check: {e}")

    print("\nAll patches applied. Restart mlx-proxy to take effect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
