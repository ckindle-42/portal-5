"""Unit tests for portal.platform.mcp_host.workspace (TASK-WORKSPACE-001)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from portal.platform.mcp_host.workspace import (
    _VALID_CATEGORIES,
    get_generated_dir,
    get_uploads_dir,
    get_workspace_root,
    resolve_upload_path,
)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point WORKSPACE_DIR at a temp directory for the duration of a test."""
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    monkeypatch.delenv("AI_OUTPUT_DIR", raising=False)
    return tmp_path


def test_get_workspace_root_uses_workspace_dir(workspace: Path) -> None:
    assert get_workspace_root() == workspace


def test_get_workspace_root_falls_back_to_ai_output_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    monkeypatch.setenv("AI_OUTPUT_DIR", str(tmp_path))
    assert get_workspace_root() == tmp_path


def test_get_uploads_dir_creates_directory(workspace: Path) -> None:
    uploads = get_uploads_dir()
    assert uploads == workspace / "uploads"
    assert uploads.is_dir()


def test_get_generated_dir_validates_category(workspace: Path) -> None:
    with pytest.raises(ValueError, match="Unknown category"):
        get_generated_dir("nonsense")


def test_get_generated_dir_creates_each_category(workspace: Path) -> None:
    for cat in _VALID_CATEGORIES:
        d = get_generated_dir(cat)
        assert d == workspace / "generated" / cat
        assert d.is_dir()


def test_resolve_upload_path_direct_match(workspace: Path) -> None:
    uploads = get_uploads_dir()
    target = uploads / "abc123.mp3"
    target.write_text("audio")
    resolved = resolve_upload_path("abc123.mp3")
    assert resolved is not None
    assert resolved == target.resolve()


def test_resolve_upload_path_prefix_match(workspace: Path) -> None:
    uploads = get_uploads_dir()
    target = uploads / "deadbeef-1234.wav"
    target.write_text("audio")
    resolved = resolve_upload_path("deadbeef-1234")
    assert resolved is not None
    assert resolved.name == "deadbeef-1234.wav"


def test_resolve_upload_path_returns_none_for_missing(workspace: Path) -> None:
    get_uploads_dir()  # ensure dir exists
    assert resolve_upload_path("nonexistent") is None


def test_resolve_upload_path_picks_most_recent_on_ambiguity(
    workspace: Path,
) -> None:
    uploads = get_uploads_dir()
    older = uploads / "id_a.txt"
    newer = uploads / "id_b.txt"
    older.write_text("old")
    older_mtime = older.stat().st_mtime
    newer.write_text("new")
    os.utime(newer, (older_mtime + 100, older_mtime + 100))
    # "id_" matches both — should prefer newer
    resolved = resolve_upload_path("id_")
    assert resolved is not None
    assert resolved.name == "id_b.txt"
