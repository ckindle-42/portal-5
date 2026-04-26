#!/usr/bin/env python3
"""Patch mlx_lm after installation to fix cross-thread stream usage (mlx >= 0.31.2).

Problem (mlx 0.31.2):
  mlx_lm.generate defines `generation_stream = mx.new_stream(mx.default_device())` at
  module import time (main thread). When mlx_lm.server's `_generate` worker thread calls
  `with mx.stream(generation_stream):` or `mx.eval()`, mlx raises:
      RuntimeError: There is no Stream(gpu, 0) in current thread.
  mlx 0.31.2 made GPU streams strictly thread-local; a Stream created in Thread-1 cannot
  be referenced in Thread-2's stream context.

Fix:
  Change `mx.new_stream(mx.default_device())` → `mx.new_thread_local_stream(mx.default_device())`
  in mlx_lm/generate.py. ThreadLocalStream is resolved per-thread at use time, so it works
  correctly in any worker thread without requiring per-thread stream initialization.

Scope: mlx_lm only. mlx_vlm uses uvicorn + asyncio (single event-loop thread) so it does
not spawn worker threads and is not affected by this issue.

Run this after any `pip install --upgrade mlx-lm` or Homebrew mlx upgrade:
    python3 scripts/patch-mlx-threads.py

The script is idempotent — safe to re-run.
"""

import re
import subprocess
import sys
from pathlib import Path


OLD = "generation_stream = mx.new_stream(mx.default_device())"
NEW = (
    "generation_stream = mx.new_thread_local_stream(mx.default_device())  "
    "# Portal5-patch: cross-thread stream fix for mlx >= 0.31.2"
)


def find_generate_py() -> Path | None:
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
        candidate = init.parent / "generate.py"
        return candidate if candidate.exists() else None
    except Exception:
        return None


def main() -> int:
    target = find_generate_py()
    if not target:
        print("ERROR: could not locate mlx_lm/generate.py", file=sys.stderr)
        return 1

    print(f"Target: {target}")
    text = target.read_text(encoding="utf-8")

    if NEW.split("  #")[0] in text:
        print("Already patched — nothing to do.")
        return 0

    if OLD not in text:
        # Check if the old pattern exists in a slightly different form
        alt = re.search(
            r"generation_stream\s*=\s*mx\.new_stream\(mx\.default_device\(\)\)",
            text,
        )
        if not alt:
            print("WARNING: expected pattern not found in generate.py.")
            print("  The mlx_lm version may have changed. Review manually.")
            print(f"  Expected:  {OLD}")
            return 1
        old_actual = alt.group()
    else:
        old_actual = OLD

    patched = text.replace(old_actual, NEW, 1)
    if patched == text:
        print("ERROR: replacement produced no change — aborting.", file=sys.stderr)
        return 1

    target.write_text(patched, encoding="utf-8")
    print("Patch applied.")
    print(f"  Before: {old_actual}")
    print(f"  After:  {NEW}")

    # Quick sanity check
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import mlx_lm.generate; print('import ok')"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            print("Sanity check: mlx_lm.generate imports ok.")
        else:
            print(f"WARNING: import check failed:\n{result.stderr}")
    except Exception as e:
        print(f"WARNING: could not run sanity check: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
