#!/usr/bin/env python3
"""Patch mlx_lm after installation to fix cross-thread stream usage (mlx >= 0.31.2)
and install Laguna architecture plugins (not upstreamed as of 2026-04-30).

Problem (mlx 0.31.2):
  mlx 0.31.2 made GPU streams strictly thread-local. Two bugs result:

  Bug 1 — generate.py (original fix):
    `generation_stream = mx.new_stream(mx.default_device())` at module import
    time (main thread). The _generate worker thread cannot use this stream:
        RuntimeError: There is no Stream(gpu, N) in current thread.

  Bug 2 — server.py (root cause):
    ModelProvider.__init__() called self.load() in the MAIN THREAD, placing
    model weights on Stream(gpu, 0). When _generate() worker thread tried to
    use the model, its stream context couldn't access the weights:
        RuntimeError: There is no Stream(gpu, 1) in current thread.

Fix 1 — generate.py:
  Change mx.new_stream() → mx.new_thread_local_stream() so the generation
  stream is resolved per-thread at use time.

Fix 2 — server.py:
  mlx-lm 0.31.2: patch ModelProvider.__init__ to defer self.load() call.
  mlx-lm 0.31.3+: upstream refactored ModelProvider to use load_default()
    called inside _generate() worker thread — no patch required, auto-detected.

Scope: mlx_lm only. mlx_vlm uses uvicorn + asyncio (single event-loop thread)
so it does not spawn worker threads and is not affected.

Run this after any `pip install --upgrade mlx-lm` or Homebrew mlx upgrade:
    python3 scripts/patch-mlx-threads.py

The script is idempotent — safe to re-run.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

# ── Laguna plugin files ───────────────────────────────────────────────────────
# mlx-lm does not ship a Laguna model (Poolside AI, never upstreamed).
# These files must be installed after any mlx-lm upgrade.
SCRIPT_DIR = Path(__file__).parent
LAGUNA_PLUGINS = [
    (SCRIPT_DIR / "mlx-model-laguna.py",       "models/laguna.py"),
    (SCRIPT_DIR / "mlx-tool-parser-laguna.py", "tool_parsers/laguna.py"),
]

# ── Patch 1: generate.py — thread-local generation stream ────────────────────

GENERATE_OLD = "generation_stream = mx.new_stream(mx.default_device())"
GENERATE_NEW = (
    "# mlx 0.31.2+: GPU streams are thread-local. new_thread_local_stream creates\n"
    "# a per-thread stream instance so the _generate worker thread gets its own\n"
    "# stream (not the main thread's), preventing RuntimeError on mx.eval.\n"
    "generation_stream = mx.new_thread_local_stream(mx.default_device())"
)

# ── Patch 2: server.py — defer model loading to worker thread (mlx-lm 0.31.2 only) ──

# mlx-lm 0.31.2 pattern: __init__ calls self.load() in main thread
SERVER_OLD_031_2 = (
    "        # Preload the default model if it is provided\n"
    "        self.default_model_map = {}\n"
    "        if self.cli_args.model is not None:\n"
    '            self.default_model_map[self.cli_args.model] = "default_model"\n'
    '            self.load(self.cli_args.model, draft_model_path="default_model")'
)

SERVER_NEW_031_2 = (
    "        # Register the default model path but defer actual loading to the\n"
    "        # generation worker thread (_generate). mlx 0.31.2+ uses thread-local GPU\n"
    "        # streams: model weights loaded in the main thread land on a stream that\n"
    "        # the generation worker cannot access, causing RuntimeError on first eval.\n"
    "        # Loading lazily in the worker ensures all weights and cache states share\n"
    "        # the same thread-local stream context.\n"
    "        self.default_model_map = {}\n"
    "        if self.cli_args.model is not None:\n"
    '            self.default_model_map[self.cli_args.model] = "default_model"\n'
    "            # DO NOT call self.load() here — deferred to _generate() worker thread"
)

# mlx-lm 0.31.3+ detection: load_default() exists AND is called inside _generate()
SERVER_031_3_SIGNAL = "def load_default(self):"
SERVER_031_3_DEFERRED = "self.model_provider.load_default()"


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
            print(
                f"  {name}: WARNING — expected pattern not found. mlx_lm version may have changed."
            )
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


def check_server_031_3(server_py: Path) -> bool:
    """Return True if server.py already has the 0.31.3+ upstream deferred-load fix."""
    text = server_py.read_text(encoding="utf-8")
    has_load_default = SERVER_031_3_SIGNAL in text
    has_deferred_call = SERVER_031_3_DEFERRED in text
    return has_load_default and has_deferred_call


def install_laguna_plugins(mlx_lm_dir: Path) -> bool:
    """Copy Laguna architecture plugins into the mlx_lm package."""
    ok = True
    for src, rel_dst in LAGUNA_PLUGINS:
        dst = mlx_lm_dir / rel_dst
        if not src.exists():
            print(f"  laguna plugin: WARNING — source {src} not found, skipping.")
            ok = False
            continue
        if dst.exists():
            # Check if already up-to-date by content comparison
            if dst.read_bytes() == src.read_bytes():
                print(f"  laguna plugin: {dst.name} already installed — nothing to do.")
                continue
        shutil.copy2(src, dst)
        print(f"  laguna plugin: installed {src.name} → {dst}")
    return ok


def main() -> int:
    ok = True

    # Detect mlx_lm package directory
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import mlx_lm; print(mlx_lm.__file__)"],
            capture_output=True, text=True, timeout=10,
        )
        mlx_lm_dir = Path(result.stdout.strip()).parent if result.returncode == 0 else None
    except Exception:
        mlx_lm_dir = None

    # Laguna plugins (before thread patches so sanity check picks them up)
    if mlx_lm_dir:
        print(f"Installing Laguna plugins into {mlx_lm_dir}")
        if not install_laguna_plugins(mlx_lm_dir):
            ok = False
    else:
        print("WARNING: could not locate mlx_lm package directory for Laguna plugins.")

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
    print(f"Checking {server_py}")
    if check_server_031_3(server_py):
        print(
            "  server.py: 0.31.3+ upstream fix detected (load_default() called in "
            "_generate worker thread) — no patch needed."
        )
    else:
        # Try the 0.31.2 patch
        if not apply_patch(server_py, SERVER_OLD_031_2, SERVER_NEW_031_2, "server.py"):
            ok = False

    if not ok:
        return 1

    # Sanity check: import generates cleanly
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import mlx_lm.generate; import mlx_lm.server; print('imports ok')",
            ],
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

    print("\nAll patches verified. Restart mlx-proxy to take effect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
