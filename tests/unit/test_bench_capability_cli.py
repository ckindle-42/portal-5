"""Unit tests for bench_capability.py CLI (fleet mode).

Uses subprocess with PYTHONPATH=. for dry-run/argparse-level checks.
No model calls — safe in CI.
"""

from __future__ import annotations

import subprocess
import sys


def _run_cli(*args: str) -> tuple[int, str]:
    """Run bench_capability.py with given args, return (exit_code, stdout_stderr)."""
    proc = subprocess.run(
        [sys.executable, "-m", "tests.benchmarks.bench_capability", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_all_dry_run_prints_workspace_count():
    """--all --dry-run prints a workspace count."""
    rc, out = _run_cli("--all", "--dry-run")
    assert rc == 0
    assert "Workspaces" in out
    # Should have a number of production workspaces (non-bench)
    import re

    m = re.search(r"Workspaces \((\d+)\)", out)
    assert m, f"No workspace count found in: {out[:200]}"
    count = int(m.group(1))
    assert count > 0, "Should have at least 1 production workspace"


def test_workspace_and_all_mutually_exclusive():
    """--workspace X --all exits non-zero (mutually exclusive)."""
    rc, out = _run_cli("--workspace", "bench-agentworld", "--all", "--dry-run")
    assert rc != 0


def test_neither_flag_exits_non_zero():
    """Neither --workspace nor --all exits non-zero (required group)."""
    rc, out = _run_cli("--dry-run")
    assert rc != 0


def test_single_workspace_dry_run_works():
    """--workspace with --dry-run exits 0."""
    rc, out = _run_cli("--workspace", "bench-agentworld", "--probe", "C1", "--dry-run")
    assert rc == 0
    assert "DRY RUN" in out
