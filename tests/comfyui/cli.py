"""CLI entry point for Portal 5 ComfyUI acceptance tests."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()


async def main() -> int:
    """Run ComfyUI acceptance tests — CLI entry point."""
    from . import _common
    from ._common import (
        _ICON,
        _comfyui_watchdog,
        _git_sha,
        _log,
        COMFYUI_URL,
        record,
    )
    from .results import _write_results
    from .runner import ALL_ORDER, _parse_sections, run_sections

    parser = argparse.ArgumentParser(description="Portal 5 — ComfyUI / Image & Video Generation Acceptance Tests")
    parser.add_argument("--section", default="ALL", help="Section(s) to run (e.g. C4, C4-C8, ALL)")
    parser.add_argument("--verbose", action="store_true", help="Print evidence lines")
    parser.add_argument("--skip-comfyui-prereqs", action="store_true", help="Skip C0 prerequisites")
    args = parser.parse_args()

    _common._verbose = args.verbose

    sections = _parse_sections(args.section)
    if args.skip_comfyui_prereqs and "C0" in sections:
        sections.remove("C0")

    sha = _git_sha()
    start = time.time()
    print(f"\n{'=' * 65}")
    print("  Portal 5 — ComfyUI / Image & Video Acceptance Tests")
    print(f"  Git: {sha}  |  Sections: {', '.join(sections)}")
    print(f"  ComfyUI: {COMFYUI_URL}")
    print(f"{'=' * 65}\n")

    watchdog_task = asyncio.create_task(_comfyui_watchdog())
    try:
        sections_run, elapsed = await run_sections(sections, verbose=args.verbose)
    finally:
        watchdog_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watchdog_task

    elapsed = int(time.time() - start)
    counts = _write_results(elapsed, sha)

    # Print summary
    print(f"\n{'─' * 65}")
    total = sum(counts.values())
    print(f"  Completed {len(sections_run)} section(s) in {elapsed}s — {total} results")
    for s in ["PASS", "FAIL", "BLOCKED", "WARN", "INFO"]:
        if s in counts:
            icon = _ICON.get(s, "  ")
            print(f"  {icon} {s}: {counts[s]}")
    print(f"{'─' * 65}\n")

    return 1 if counts.get("FAIL", 0) or counts.get("BLOCKED", 0) else 0
