#!/usr/bin/env python3
"""Re-pin spine units whose cited sources moved since their last pin.

`check_spine_drift` (BS, enforced by the pre-push hook) hard-fails the moment
HEAD advances past a unit's `last_generated_commit` while any of its cited
paths changed in between. That is unavoidable on *every* commit that touches
a cited file: a unit cannot be pinned to a commit hash that does not exist
yet, so "update fact-units in the same task" (CLAUDE.md Rule 12) always means
two commits — the functional change, then this tool's pin bump — never one.

This tool changes `last_generated_commit` only. It never touches unit body,
sources, or claims: if the census reports a unit stale *and* a real fact
changed, edit that unit by hand first (this script would otherwise pin over
a doc that is now wrong, not just old).

Usage:
    python3 scripts/repin_stale.py            # dry run, lists what would change
    python3 scripts/repin_stale.py --apply    # writes the pin bumps
    python3 scripts/repin_stale.py --apply --commit <sha>  # pin to <sha> instead of HEAD
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from portal.platform.wiki.drift import pin_health
from portal.platform.wiki.store import load_all, save_unit


def _head(repo_root: Path) -> str:
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return r.stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--apply", action="store_true", help="write the pin bumps (default: dry run)")
    ap.add_argument("--commit", default=None, help="pin to this SHA instead of HEAD")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    target = args.commit or _head(repo_root)

    units = {u.id: u for u in load_all()}
    ph = pin_health(repo_root, list(units.values()))

    if not ph.stale:
        print("[repin] no stale units — nothing to do")
        return 0

    print(f"[repin] {len(ph.stale)} stale unit(s) -> {target[:8]}")
    for uid in ph.stale:
        print(f"  {uid}")

    if not args.apply:
        print("\n[repin] dry run — re-run with --apply to write these pins")
        return 0

    for uid in ph.stale:
        save_unit(replace(units[uid], last_generated_commit=target))

    print(f"\n[repin] wrote {len(ph.stale)} pin(s). Commit this as its own change, e.g.:")
    print(
        "  git add portal_wiki/canonical/ && git commit -m"
        ' "chore(spine): re-pin units stale after <this-change>"'
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
