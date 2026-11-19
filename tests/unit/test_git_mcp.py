"""Git MCP (:8950) — read tools, commit/push, live-checkout guard. No network."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from portal.modules.orchestration.mcp import git_mcp  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def _run_git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def _repo(tmp_path: Path, *names: str) -> Path:
    """One committed repo with one file per name."""
    root = tmp_path / "work"
    root.mkdir(parents=True)
    _run_git(root, "init", "-q")
    _run_git(root, "config", "user.email", "t@example.test")
    _run_git(root, "config", "user.name", "t")
    for name in names:
        (root / name).write_text(f"content of {name}\n", encoding="utf-8")
    _run_git(root, "add", ".")
    _run_git(root, "commit", "-q", "-m", "seed")
    return root


def _call(tool, **kwargs: str) -> dict[str, object]:
    return asyncio.run(tool(**kwargs))  # type: ignore[arg-type]


def test_status_reads_a_foreign_repo(tmp_path: Path) -> None:
    root = _repo(tmp_path, "a.txt")
    (root / "a.txt").write_text("changed\n", encoding="utf-8")
    result = _call(git_mcp.git_status, repo_path=str(root))
    assert result["success"] is True
    assert " M a.txt" in str(result["data"])


def test_log_returns_commit_records(tmp_path: Path) -> None:
    root = _repo(tmp_path, "a.txt")
    result = _call(git_mcp.git_log, repo_path=str(root), max_count="3")
    assert result["success"] is True
    commits = result["data"]
    assert isinstance(commits, list) and len(commits) == 1
    assert commits[0]["subject"] == "seed"  # type: ignore[index]


def test_diff_reports_working_tree_changes(tmp_path: Path) -> None:
    root = _repo(tmp_path, "a.txt")
    (root / "a.txt").write_text("changed content\n", encoding="utf-8")
    result = _call(git_mcp.git_diff, repo_path=str(root))
    assert result["success"] is True
    assert "changed content" in str(result["data"])


def test_commit_stages_named_files_and_push_reaches_a_local_remote(tmp_path: Path) -> None:
    root = _repo(tmp_path, "a.txt")
    (root / "c.txt").write_text("third\n", encoding="utf-8")
    remote = tmp_path / "remote.git"
    _run_git(tmp_path, "clone", "-q", "--bare", str(root), str(remote))
    _run_git(root, "remote", "add", "origin", str(remote))
    committed = _call(
        git_mcp.git_commit,
        repo_path=str(root),
        message="add c",
        files=["c.txt"],
    )
    assert committed["success"] is True, committed
    pushed = _call(git_mcp.git_push, repo_path=str(root), remote="origin")
    assert pushed["success"] is True, pushed
    remote_heads = _run_git(remote, "rev-parse", "HEAD")
    local_head = _run_git(root, "rev-parse", "HEAD")
    assert remote_heads == local_head


def test_the_live_checkout_is_refused(tmp_path: Path) -> None:
    live = git_mcp._live_checkout()
    for tool, kwargs in (
        (git_mcp.git_status, {}),
        (git_mcp.git_commit, {"message": "no"}),
        (git_mcp.git_push, {}),
    ):
        result = _call(tool, repo_path=str(live), **kwargs)
        assert result["success"] is False
        assert "live Portal checkout" in str(result["error"])
    nested = _call(git_mcp.git_status, repo_path=str(live / "portal"))
    assert nested["success"] is False


def test_allow_root_confines_every_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inside = _repo(tmp_path, "a.txt")
    outside = _repo(tmp_path / "elsewhere", "b.txt")
    monkeypatch.setenv("GIT_MCP_ALLOW_ROOT", str(tmp_path))
    assert _call(git_mcp.git_status, repo_path=str(inside))["success"] is True
    monkeypatch.setenv("GIT_MCP_ALLOW_ROOT", str(tmp_path / "work"))
    result = _call(git_mcp.git_status, repo_path=str(outside))
    assert result["success"] is False
    assert "GIT_MCP_ALLOW_ROOT" in str(result["error"])


def test_flag_shaped_arguments_are_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path, "a.txt")
    pushed = _call(git_mcp.git_push, repo_path=str(root), remote="--upload-pack=evil")
    assert pushed["success"] is False


def test_health_route_answers() -> None:
    import json

    from starlette.testclient import TestClient

    client = TestClient(git_mcp.mcp.streamable_http_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert json.loads(response.text)["status"] == "ok"


def test_repo_path_must_be_absolute(tmp_path: Path) -> None:
    result = _call(git_mcp.git_status, repo_path="relative/path")
    assert result["success"] is False
    assert "absolute" in str(result["error"])
