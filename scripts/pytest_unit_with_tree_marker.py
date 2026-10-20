#!/usr/bin/env python3
"""pre-commit pytest-unit: run tests/unit unchanged; on success record the tree for check H."""

from __future__ import annotations

import subprocess
import sys

CMD = ["uv", "run", "pytest", "tests/unit", "-n", "auto", "-x", "--tb=short", "-q"]


def marker_path() -> str:
    """Per-checkout marker (`.git` is a file in a worktree, so ask git where it lives)."""
    return subprocess.run(
        ["git", "rev-parse", "--git-path", "portal5_unit_pass"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def main() -> int:
    rc = subprocess.run(CMD).returncode
    if rc == 0:
        tree = subprocess.run(["git", "write-tree"], capture_output=True, text=True, check=True)
        with open(marker_path(), "w", encoding="utf-8") as f:
            f.write(tree.stdout.strip() + "\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
