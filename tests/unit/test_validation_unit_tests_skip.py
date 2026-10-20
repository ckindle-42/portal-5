"""H check — skip when pytest-unit already passed for the current tree."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from scripts.validation.inference import check_unit_tests


def test_skip_on_matching_clean_tree(tmp_path: Path) -> None:
    """When the marker matches HEAD^{tree} and status is clean, returns PASS without running pytest."""
    repo = tmp_path
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "a.txt").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "first"], check=True)

    tree = subprocess.run(
        ["git", "write-tree"], capture_output=True, text=True, cwd=str(repo)
    ).stdout.strip()
    marker = Path(repo) / ".git" / "portal5_unit_pass"
    marker.write_text(tree + "\n", encoding="utf-8")

    import scripts.validation.inference as inf

    original_root = inf.REPO_ROOT
    inf.REPO_ROOT = repo
    try:
        status, detail, sub = check_unit_tests()
        assert status == "PASS"
        assert f"tests/unit already passed for tree {tree}" in detail
        assert sub == []
    finally:
        inf.REPO_ROOT = original_root


def test_runs_when_marker_mismatch(tmp_path: Path) -> None:
    """When the marker does not match HEAD^{tree}, check runs the suite."""
    repo = tmp_path
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "a.txt").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "first"], check=True)

    wrong_tree = "0" * 40
    marker = Path(repo) / ".git" / "portal5_unit_pass"
    marker.write_text(wrong_tree + "\n", encoding="utf-8")

    import scripts.validation.inference as inf

    original_root = inf.REPO_ROOT
    inf.REPO_ROOT = repo
    try:
        with patch("scripts.validation.inference.subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "= 5 passed =\n"})()
            status, detail, sub = check_unit_tests()
            assert status == "PASS"
            assert "already passed" not in detail
    finally:
        inf.REPO_ROOT = original_root


def test_runs_when_dirty_tree(tmp_path: Path) -> None:
    """When git status is dirty, check runs the suite even if marker matches."""
    repo = tmp_path
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "a.txt").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "first"], check=True)

    tree = subprocess.run(
        ["git", "write-tree"], capture_output=True, text=True, cwd=str(repo)
    ).stdout.strip()
    marker = Path(repo) / ".git" / "portal5_unit_pass"
    marker.write_text(tree + "\n", encoding="utf-8")
    (repo / "dirty.txt").write_text("modified")

    import scripts.validation.inference as inf

    original_root = inf.REPO_ROOT
    inf.REPO_ROOT = repo
    try:
        with patch("scripts.validation.inference.subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "= 5 passed =\n"})()
            status, detail, sub = check_unit_tests()
            assert status == "PASS"
            assert "already passed" not in detail
    finally:
        inf.REPO_ROOT = original_root


def test_runs_when_no_marker(tmp_path: Path) -> None:
    """When the marker does not exist, check runs the suite."""
    repo = tmp_path
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "a.txt").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "first"], check=True)

    import scripts.validation.inference as inf

    original_root = inf.REPO_ROOT
    inf.REPO_ROOT = repo
    try:
        with patch("scripts.validation.inference.subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "= 5 passed =\n"})()
            status, detail, sub = check_unit_tests()
            assert status == "PASS"
            assert "already passed" not in detail
    finally:
        inf.REPO_ROOT = original_root
