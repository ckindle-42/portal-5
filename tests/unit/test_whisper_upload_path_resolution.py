"""Whisper/STT upload path resolution — the live Stage-2 defect this covers:

  Tool loop hop=1 tool=transcribe_with_speakers error=file not found at path:
  /workspace/uploads/8527a06e-9749-416f-9ee2-333c3e2e583a_sample_two_speakers.wav

The model quotes the OWUI container mount (/workspace/...) while the MLX
transcribe server resolves on the host, where the same file lives under
$AI_OUTPUT_DIR. Hermetic: fake workspace in tmp_path, no MLX, no network, no
server started.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TRANSCRIBE = REPO / "scripts" / "mlx-transcribe.py"
WHISPER_MCP = REPO / "portal" / "modules" / "media" / "tools" / "whisper_mcp.py"

_spec = importlib.util.spec_from_file_location("mlx_transcribe_upload_test", TRANSCRIBE)
assert _spec is not None and _spec.loader is not None
transcribe = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("mlx_transcribe_upload_test", transcribe)
_spec.loader.exec_module(transcribe)

_whisper_spec = importlib.util.spec_from_file_location("whisper_mcp_upload_test", WHISPER_MCP)
assert _whisper_spec is not None and _whisper_spec.loader is not None
whisper_mcp = importlib.util.module_from_spec(_whisper_spec)
sys.modules.setdefault("whisper_mcp_upload_test", whisper_mcp)
_whisper_spec.loader.exec_module(whisper_mcp)


UUID = "8527a06e-9749-416f-9ee2-333c3e2e583a"
STORED = f"{UUID}_sample_two_speakers.wav"


@pytest.fixture()
def uploads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "AI_Output"
    monkeypatch.setenv("AI_OUTPUT_DIR", str(root))
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    up = root / "uploads"
    up.mkdir(parents=True)
    return up


def _write_audio(up: Path, name: str, age_s: float = 0.0) -> Path:
    p = up / name
    p.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 8)
    stamp = time.time() - age_s
    os.utime(p, (stamp, stamp))
    return p


def test_container_workspace_path_resolves_on_host(uploads: Path) -> None:
    _write_audio(uploads, STORED)
    path, name = transcribe._resolve_audio_input(f"/workspace/uploads/{STORED}")
    assert path is not None and path.is_file()
    assert path == uploads / STORED
    assert name == STORED


def test_absolute_host_path_still_resolves(uploads: Path, tmp_path: Path) -> None:
    outside = _write_audio(tmp_path, "host_clip.wav")
    path, name = transcribe._resolve_audio_input(str(outside))
    assert path == outside.resolve()
    assert name == "host_clip.wav"


def test_unknown_absolute_path_falls_back_to_uploads_basename(uploads: Path) -> None:
    """A path that exists nowhere as-is still resolves when its basename is an
    upload (OWUI may hand the model a container path of a re-stored file)."""
    _write_audio(uploads, STORED)
    path, _ = transcribe._resolve_audio_input(f"/app/uploads/{STORED}")
    assert path == uploads / STORED


def test_bare_stored_name_and_original_name_resolve(uploads: Path) -> None:
    _write_audio(uploads, STORED)
    path, _ = transcribe._resolve_audio_input(STORED)
    assert path == uploads / STORED
    path, _ = transcribe._resolve_audio_input("sample_two_speakers.wav")
    assert path == uploads / STORED


def test_omitted_argument_auto_detects_latest_upload(uploads: Path) -> None:
    _write_audio(uploads, f"aaa_{UUID}_old.wav", age_s=100)
    latest = _write_audio(uploads, STORED)
    path, name = transcribe._resolve_audio_input(None)
    assert path == latest
    assert name == STORED


def test_empty_and_unknown_references_are_errors(uploads: Path) -> None:
    _write_audio(uploads, STORED)
    path, err = transcribe._resolve_audio_input("")
    assert path is None
    assert "file not found" in err
    path, err = transcribe._resolve_audio_input("missing.wav")
    assert path is None
    assert "file not found" in err


def test_whisper_docker_fallback_resolves_owui_names(uploads: Path) -> None:
    _write_audio(uploads, STORED)
    assert whisper_mcp._resolve_local_audio(STORED) == uploads / STORED
    assert whisper_mcp._resolve_local_audio("sample_two_speakers.wav") == uploads / STORED
    assert whisper_mcp._resolve_local_audio(str(uploads / STORED)) == uploads / STORED
    assert whisper_mcp._resolve_local_audio(f"{UUID}") == uploads / STORED
    assert whisper_mcp._resolve_local_audio("missing.wav") is None


def test_transcript_docx_sidecar_gets_an_owui_download_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AI_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    tdir = tmp_path / "generated" / "transcripts"
    tdir.mkdir(parents=True)
    for suffix in ("json", "md", "docx"):
        (tdir / f"transcript_abc.{suffix}").write_bytes(b"x")

    async def fake_publish(path: Path) -> dict[str, str]:
        return {"url": f"/api/v1/files/fake-id/content/{path.name}", "filename": path.name}

    monkeypatch.setattr(whisper_mcp, "publish_file", fake_publish)
    res = {
        "json_path": "/host/out/transcript_abc.json",
        "md_path": "/host/out/transcript_abc.md",
        "docx_path": "/host/out/transcript_abc.docx",
    }
    out = asyncio.run(whisper_mcp._attach_transcript_urls(res))
    assert out["docx_url"].endswith("transcript_abc.docx")
    assert out["md_url"].endswith("transcript_abc.md")
    assert out["json_url"].endswith("transcript_abc.json")
