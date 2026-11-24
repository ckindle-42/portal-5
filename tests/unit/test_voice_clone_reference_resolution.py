"""clone_voice reference-audio resolution — the live s2-p6-voice-clone defect:

  Tool loop hop=1 tool=clone_voice error=Could not decode reference audio:
  ffmpeg ... voiceref_we57_rf4.json ... exit status 183

OWUI's STT pre-processing writes a <uuid>_<name>.json sidecar (and an .mp3
conversion) next to every audio upload. The sidecar is newer than the .wav,
so a uuid-prefix reference resolved to JSON and was handed to ffmpeg. Also
covers the host-side /workspace/... rebase and the JSON-not-audio guard.
Hermetic: fake workspace in tmp_path, no MLX, no network, no server started.
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
TTS_MCP = REPO / "portal" / "modules" / "media" / "tools" / "tts_mcp.py"
SPEECH = REPO / "scripts" / "mlx-speech.py"

_tts_spec = importlib.util.spec_from_file_location("tts_mclone_ref_test", TTS_MCP)
assert _tts_spec is not None and _tts_spec.loader is not None
tts_mcp = importlib.util.module_from_spec(_tts_spec)
sys.modules.setdefault("tts_mclone_ref_test", tts_mcp)
_tts_spec.loader.exec_module(tts_mcp)

_speech_spec = importlib.util.spec_from_file_location("mlx_speech_clone_ref_test", SPEECH)
assert _speech_spec is not None and _speech_spec.loader is not None
speech = importlib.util.module_from_spec(_speech_spec)
sys.modules.setdefault("mlx_speech_clone_ref_test", speech)
_speech_spec.loader.exec_module(speech)

UUID = "3131ff0e-9727-4c5a-8ec2-1f9e505f942d"
STEM = f"{UUID}_sample_two_speakers"
STORED = f"{STEM}.wav"
SIDECAR = f"{STEM}.json"


@pytest.fixture()
def uploads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "AI_Output"
    monkeypatch.setenv("AI_OUTPUT_DIR", str(root))
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    up = root / "uploads"
    up.mkdir(parents=True)
    return up


def _write(up: Path, name: str, content: bytes, age_s: float = 0.0) -> Path:
    p = up / name
    p.write_bytes(content)
    stamp = time.time() - age_s
    os.utime(p, (stamp, stamp))
    return p


def _upload_with_sidecar(up: Path) -> Path:
    """The live layout: wav first, then the newer STT JSON sidecar + mp3."""
    wav = _write(up, STORED, b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 8, age_s=60)
    _write(up, f"{STEM}.mp3", b"ID3\x00\x00", age_s=5)
    _write(up, SIDECAR, b'{"text":"hello"}', age_s=0)
    return wav


def test_uuid_prefix_resolves_audio_not_json_sidecar(uploads: Path) -> None:
    wav = _upload_with_sidecar(uploads)
    hit = tts_mcp._resolve_reference(UUID)
    assert hit is not None
    assert hit.suffix.lower() in tts_mcp._AUDIO_EXTS
    assert hit.stem == wav.stem


def test_stored_name_and_container_path_resolve(uploads: Path) -> None:
    wav = _upload_with_sidecar(uploads)
    assert tts_mcp._resolve_reference(STORED) == wav
    assert tts_mcp._resolve_reference(f"/workspace/uploads/{STORED}") == wav


def test_owui_content_url_resolves_audio_not_json_sidecar(uploads: Path) -> None:
    wav = _upload_with_sidecar(uploads)
    hit = tts_mcp._resolve_reference(f"/api/v1/files/{UUID}/content/{STORED}")
    assert hit is not None and hit.stem == wav.stem
    assert hit.suffix.lower() in tts_mcp._AUDIO_EXTS


def test_json_only_reference_never_reaches_ffmpeg(uploads: Path) -> None:
    _write(uploads, SIDECAR, b'{"text":"hello"}')
    assert tts_mcp._resolve_reference(UUID) is None
    assert tts_mcp._resolve_reference(SIDECAR) is None


def test_empty_reference_picks_latest_audio_not_sidecar(uploads: Path) -> None:
    _upload_with_sidecar(uploads)
    hit = tts_mcp._resolve_reference("")
    assert hit is not None and hit.suffix.lower() in tts_mcp._AUDIO_EXTS


@pytest.mark.parametrize("reference_text", [None, "", "These are the exact words in the clip."])
def test_clone_voice_registers_audio_and_caller_reference_text(
    uploads: Path, monkeypatch: pytest.MonkeyPatch, reference_text: str | None
) -> None:
    wav = _upload_with_sidecar(uploads)
    captured: dict[str, object] = {}

    async def fake_register(name: str, ref: Path | None, raw: str, text: str) -> dict:
        captured["ref"] = ref
        captured["reference_text"] = text
        return {"status": "success", "profile": name}

    async def fake_speak(text: str, voice: str) -> dict:
        captured["voice"] = voice
        return {"status": "success", "download_url": "/api/v1/files/x/content/y.wav"}

    monkeypatch.setattr(tts_mcp, "_post_register", fake_register)
    monkeypatch.setattr(tts_mcp, "_speech_speak", fake_speak)
    kwargs = {} if reference_text is None else {"reference_text": reference_text}
    out = asyncio.run(tts_mcp.clone_voice(reference_audio=UUID, text="say hi", **kwargs))
    assert out.get("status") == "success"
    ref = captured["ref"]
    assert isinstance(ref, Path)
    assert ref.stem == wav.stem and ref.suffix.lower() in tts_mcp._AUDIO_EXTS
    assert captured["reference_text"] == (reference_text or "")
    assert captured["reference_text"] != "one-off clone reference"


def test_host_rebases_container_workspace_path(uploads: Path) -> None:
    wav = _upload_with_sidecar(uploads)
    assert speech._resolve_host_ref(f"/workspace/uploads/{STORED}") == wav
    assert speech._resolve_host_ref(str(wav)) == wav
    assert speech._resolve_host_ref("/workspace/uploads/missing.wav") is None


def test_read_audio_any_rejects_json_with_clear_error(uploads: Path) -> None:
    sidecar = _write(uploads, SIDECAR, b'{"text":"hello"}')
    with pytest.raises(ValueError, match="JSON"):
        speech._read_audio_any(sidecar)


def test_register_voice_profile_rejects_json_sidecar(uploads: Path) -> None:
    sidecar = _write(uploads, SIDECAR, b'{"text":"hello"}')
    out = speech.register_voice_profile("qat-json-ref", str(sidecar), "hello")
    assert "error" in out and "JSON" in out["error"]


def test_register_voice_profile_accepts_empty_reference_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys
    import types

    import numpy as np

    source = tmp_path / "reference.wav"
    source.write_bytes(b"RIFF")
    profile = tmp_path / "profiles" / "qat-empty-ref"
    monkeypatch.setattr(speech, "_profile_dir", lambda _name: profile)
    monkeypatch.setattr(
        speech,
        "_read_audio_any",
        lambda _src: (np.zeros(5 * 16000, dtype=np.float32), 16000),
    )
    fake_sf = types.SimpleNamespace(write=lambda path, _audio, _sr: Path(path).write_bytes(b"RIFF"))
    monkeypatch.setitem(sys.modules, "soundfile", fake_sf)

    out = speech.register_voice_profile("qat-empty-ref", str(source), "")

    assert out["status"] == "success"
    assert (profile / "reference.txt").read_text(encoding="utf-8") == ""
