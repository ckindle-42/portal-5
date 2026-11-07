"""AE's launcher sub-check must not fail a push from a fresh worktree.

The launcher is gitignored (it exists only in the operator's live checkout), so
a merge worktree made from HEAD can never contain it (merge 4f57811cf's push
was refused for exactly this). Absent+ignored is a WARN naming the path; a
tracked launcher that vanished stays a FAIL.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.validation.security_bench import _LAUNCHER, _launcher_sub


def _repo(tmp_path: Path, ignore: bool) -> Path:
    """Throwaway git checkout, optionally ignoring the launcher path."""
    if ignore:
        (tmp_path / ".gitignore").write_text(f"/{_LAUNCHER}\n", encoding="utf-8")
    git = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def test_ignored_and_absent_is_warn_not_fail(tmp_path: Path) -> None:
    root = _repo(tmp_path, ignore=True)
    sub = _launcher_sub(root)
    assert sub["status"] == "WARN"
    assert "not present in this checkout" in sub["detail"]
    assert _LAUNCHER in sub["detail"]


def test_present_executable_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path, ignore=False)
    launcher = root / _LAUNCHER
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o755)
    sub = _launcher_sub(root)
    assert sub["status"] == "PASS"
    assert sub["detail"] == str(launcher)


def test_present_not_executable_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path, ignore=False)
    launcher = root / _LAUNCHER
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o644)
    sub = _launcher_sub(root)
    assert sub["status"] == "FAIL"
    assert "not executable" in sub["detail"]


def test_absent_and_not_ignored_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path, ignore=False)
    sub = _launcher_sub(root)
    assert sub["status"] == "FAIL"
    assert "launcher not found" in sub["detail"]
    assert _LAUNCHER in sub["detail"]


def test_check_is_registered() -> None:
    from scripts.validation import all_checks

    assert any(slug == "bench_supervisor" for slug, _label, _fn in all_checks())
