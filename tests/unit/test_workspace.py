"""Unit tests for portal.platform.mcp_host.workspace (TASK-WORKSPACE-001)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from portal.platform.mcp_host.workspace import (
    _VALID_CATEGORIES,
    assert_public_http_url,
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


def test_resolve_upload_path_rejects_absolute_path_escape(
    workspace: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """An absolute path must not bypass the uploads dir via pathlib's
    Path(a) / "/b" == Path("/b") join semantics — this is an LLM-controlled
    tool argument, not a trusted identifier (see comfyui_mcp.py's
    _upload_image_to_comfyui security fix)."""
    get_uploads_dir()
    secret_dir = tmp_path_factory.mktemp("outside_uploads")
    secret = secret_dir / "secret.txt"
    secret.write_text("do not read me")
    assert resolve_upload_path(str(secret)) is None


def test_resolve_upload_path_rejects_traversal(workspace: Path) -> None:
    outside = workspace.parent / "outside_secret.txt"
    outside.write_text("secret")
    assert resolve_upload_path(f"../{outside.name}") is None


def _fake_getaddrinfo(ip: str):
    """Build a socket.getaddrinfo-shaped return value for a single IP, so
    these tests don't depend on real DNS/network access (tests/unit/ must
    pass offline)."""
    return [(2, 1, 6, "", (ip, 0))]


def test_assert_public_http_url_accepts_public_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: _fake_getaddrinfo("93.184.216.34"))
    assert_public_http_url("https://example.com/image.png")  # must not raise


def test_assert_public_http_url_rejects_loopback_ip_literal() -> None:
    with pytest.raises(ValueError, match="non-public address"):
        assert_public_http_url("http://127.0.0.1:8080/secret")


def test_assert_public_http_url_rejects_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: _fake_getaddrinfo("127.0.0.1"))
    with pytest.raises(ValueError, match="non-public address"):
        assert_public_http_url("http://localhost/secret")


def test_assert_public_http_url_rejects_link_local_metadata_ip_literal() -> None:
    with pytest.raises(ValueError, match="non-public address"):
        assert_public_http_url("http://169.254.169.254/latest/meta-data/")


def test_assert_public_http_url_rejects_private_range_ip_literal() -> None:
    with pytest.raises(ValueError, match="non-public address"):
        assert_public_http_url("http://10.0.0.5/internal")


def test_assert_public_http_url_rejects_hostname_resolving_to_private_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: _fake_getaddrinfo("192.168.1.1"))
    with pytest.raises(ValueError, match="non-public address"):
        assert_public_http_url("http://internal.corp.example/secret")


def test_assert_public_http_url_rejects_non_http_scheme() -> None:
    with pytest.raises(ValueError, match="must be http"):
        assert_public_http_url("file:///etc/passwd")


def test_assert_public_http_url_rejects_unresolvable_host(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def _raise(host, port):
        raise socket.gaierror("mocked: name resolution failure")

    monkeypatch.setattr("socket.getaddrinfo", _raise)
    with pytest.raises(ValueError, match="does not resolve"):
        assert_public_http_url("http://this-host-should-not-exist.invalid/x")
