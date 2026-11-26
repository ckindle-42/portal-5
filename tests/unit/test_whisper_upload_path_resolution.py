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
import shutil
import subprocess
import sys
import time
import wave
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


def _write_pcm_wav(path: Path, sample_rate: int = 24000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\0\0" * sample_rate)
    return path


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


def test_generated_speech_download_link_resolves_to_workspace_audio(uploads: Path) -> None:
    name = "speak_sample.wav"
    generated = _write_pcm_wav(uploads.parent / "generated" / "speech" / name)
    link = f"https://portal.example/api/v1/files/published-id/content/{name}"

    for reference in (link, f"[Download audio]({link})"):
        path, source_name = transcribe._resolve_audio_input(reference)
        assert path == generated
        assert source_name == name


def test_owui_download_link_resolves_upload_file_id(uploads: Path) -> None:
    uploaded = _write_audio(uploads, STORED)
    link = f"https://portal.example/api/v1/files/{UUID}/content/{STORED}"

    path, source_name = transcribe._resolve_audio_input(link)

    assert path == uploaded
    assert source_name == STORED


def test_generated_pcm_wav_keeps_its_observed_sample_rate(
    monkeypatch: pytest.MonkeyPatch, uploads: Path
) -> None:
    generated = _write_pcm_wav(uploads.parent / "generated" / "speech" / "speak_sample.wav")
    monkeypatch.setattr(shutil, "which", lambda _name: pytest.fail("ffmpeg should not run"))

    with transcribe._decoded_audio_path(str(generated)) as decoded:
        assert Path(decoded) == generated
        with wave.open(decoded, "rb") as audio:
            assert audio.getframerate() == 24000
            assert audio.getnchannels() == 1
            assert audio.getsampwidth() == 2


def test_unsupported_audio_is_converted_to_pcm_wav(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "generated.webm"
    source.write_bytes(b"unsupported container")
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        _write_pcm_wav(Path(command[-1]), sample_rate=16000)
        return subprocess.CompletedProcess(command, 0, "", "")

    def reject_miniaudio(_path: Path) -> None:
        raise ValueError("unsupported file format")

    monkeypatch.setattr(transcribe, "_probe_audio_file", reject_miniaudio)
    monkeypatch.setattr(shutil, "which", lambda _name: "ffmpeg")
    monkeypatch.setattr(subprocess, "run", fake_run)

    with transcribe._decoded_audio_path(str(source)) as decoded:
        assert Path(decoded) != source
        with wave.open(decoded, "rb") as audio:
            assert audio.getframerate() == 16000
            assert audio.getnchannels() == 1
            assert audio.getsampwidth() == 2

    assert commands[0][0] == "ffmpeg"
    assert "-i" in commands[0]
    assert commands[0][commands[0].index("-i") + 1] == str(source)
    assert commands[0][commands[0].index("-ac") + 1] == "1"
    assert commands[0][commands[0].index("-ar") + 1] == "16000"
    assert commands[0][commands[0].index("-c:a") + 1] == "pcm_s16le"
    assert not Path(decoded).exists()


def test_failed_ffmpeg_conversion_reports_actual_decode_cause(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "broken.webm"
    source.write_bytes(b"not media")

    def reject_miniaudio(_path: Path) -> None:
        raise ValueError("unsupported file format")

    monkeypatch.setattr(transcribe, "_probe_audio_file", reject_miniaudio)
    monkeypatch.setattr(shutil, "which", lambda _name: "ffmpeg")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 1, "", "Invalid data found when processing input"
        ),
    )

    with (
        pytest.raises(ValueError, match="broken.webm.*Invalid data found"),
        transcribe._decoded_audio_path(str(source)),
    ):
        pass


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


def _fake_docx(segments: list, meta: dict, source_name: str, path: Path) -> bool:
    path.write_bytes(b"docx-bytes")
    return True


def test_host_transcribe_publishes_sidecars_as_owui_urls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The pipeline dispatches transcribe_with_speakers to the host-native
    :8924 MCP (fleet precedence over whisper), so the host itself must mint
    the OWUI download links — its own :8924/files URLs are not browser-reachable
    and never match the QAT artifact check."""
    monkeypatch.setenv("AI_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    monkeypatch.setattr(transcribe, "_write_docx", _fake_docx)
    published: list[str] = []

    def fake_publish(path: Path) -> dict[str, str]:
        published.append(Path(path).name)
        return {"url": f"/api/v1/files/fake-id/content/{Path(path).name}"}

    monkeypatch.setattr(transcribe, "publish_file_sync", fake_publish)
    out = transcribe._persist_transcript([], {"duration": 1.0, "language": "en"}, "clip.wav")
    assert out["docx_url"].startswith("/api/v1/files/")
    assert out["docx_url"].endswith(".docx")
    assert out["md_url"].startswith("/api/v1/files/")
    assert out["json_url"].startswith("/api/v1/files/")
    assert sorted(published) == sorted(
        Path(out[k]).name for k in ("json_path", "md_path", "docx_path")
    )


def test_host_transcribe_publish_failure_keeps_host_url_and_warns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AI_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    monkeypatch.setattr(transcribe, "_write_docx", _fake_docx)
    monkeypatch.setattr(
        transcribe, "publish_file_sync", lambda path: {"error": "OWUI_API_KEY is not set"}
    )
    out = transcribe._persist_transcript([], {"duration": 1.0, "language": "en"}, "clip.wav")
    assert ":8924/files/" in out["docx_url"]
    assert "OWUI_API_KEY" in out["warning"]


def test_host_transcribe_eval_scope_does_not_publish(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A WFE row writes only inside its own namespace — never into the live
    OWUI file store."""
    monkeypatch.setenv("AI_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    monkeypatch.setattr(transcribe, "_write_docx", _fake_docx)

    def boom(path: Path) -> dict[str, str]:
        raise AssertionError("eval scope must not publish to OWUI")

    monkeypatch.setattr(transcribe, "publish_file_sync", boom)
    scope = transcribe.eval_scope.parse(
        {"campaign": "wfe_0123456789abcdef", "run": "wfe_fedcba9876543210", "allow": []}
    )
    token = transcribe.eval_scope.EVAL_SCOPE.set(scope)
    try:
        out = transcribe._persist_transcript([], {"duration": 1.0, "language": "en"}, "clip.wav")
    finally:
        transcribe.eval_scope.EVAL_SCOPE.reset(token)
    assert ":8924/files/" in out["docx_url"]
