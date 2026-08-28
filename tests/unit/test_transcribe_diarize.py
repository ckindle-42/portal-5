"""Unit tests for mlx-transcribe deterministic helpers.

Covers the VibeVoice segment adapter, markdown formatting, and file resolution.
Model loading and audio I/O are out of scope (acceptance tests S9-03..05 cover those).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "mlx-transcribe.py"


@pytest.fixture(scope="module")
def transcribe_module():
    """Load mlx-transcribe.py with heavy deps stubbed."""
    sys.modules.setdefault("mlx_audio", type(sys)("mlx_audio"))
    stt = type(sys)("mlx_audio.stt")
    utils = type(sys)("mlx_audio.stt.utils")
    utils.load = lambda *a, **k: None  # type: ignore[attr-defined]
    sys.modules.setdefault("mlx_audio.stt", stt)
    sys.modules.setdefault("mlx_audio.stt.utils", utils)

    spec = importlib.util.spec_from_file_location("mlx_transcribe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_adapter_parsed_shape(transcribe_module):
    segs = [
        {"start_time": 0.0, "end_time": 2.0, "speaker_id": 0, "text": " Hello "},
        {"start_time": 2.0, "end_time": 4.0, "speaker_id": 1, "text": "World"},
    ]
    out = transcribe_module._vibevoice_segments_to_canonical(segs)
    assert out[0] == {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00", "text": "Hello"}
    assert out[1]["speaker"] == "SPEAKER_01"


def test_adapter_bare_parsed_shape(transcribe_module):
    """Phase 0 confirmed this build emits bare start/end/speaker_id/text."""
    segs = [{"start": 0, "end": 14.16, "speaker_id": 0, "text": "Hello everyone"}]
    out = transcribe_module._vibevoice_segments_to_canonical(segs)
    assert out[0] == {"start": 0.0, "end": 14.16, "speaker": "SPEAKER_00", "text": "Hello everyone"}


def test_adapter_raw_shape(transcribe_module):
    segs = [{"Start": 0.0, "End": 5.2, "Speaker": 0, "Content": "Hello everyone"}]
    out = transcribe_module._vibevoice_segments_to_canonical(segs)
    assert out[0]["speaker"] == "SPEAKER_00"
    assert out[0]["text"] == "Hello everyone"
    assert out[0]["end"] == 5.2


def test_adapter_missing_speaker(transcribe_module):
    out = transcribe_module._vibevoice_segments_to_canonical(
        [{"start": 0.0, "end": 1.0, "text": "x"}]
    )
    assert out[0]["speaker"] == "SPEAKER_UNKNOWN"


def test_format_markdown_includes_metadata(transcribe_module):
    merged = [
        {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00", "text": "Hello there"},
        {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01", "text": "General Kenobi"},
    ]
    meta = {"duration": 10.0, "language": "en", "speaker_count": 2}
    md = transcribe_module._format_markdown(merged, meta, "audio.wav")
    assert "Transcript: audio.wav" in md
    assert "**Speakers**: 2" in md
    assert "**SPEAKER_00**" in md


def test_format_markdown_timestamps(transcribe_module):
    merged = [{"start": 65.0, "end": 70.0, "speaker": "SPEAKER_00", "text": "After a minute"}]
    meta = {"duration": 70.0, "language": "en", "speaker_count": 1}
    md = transcribe_module._format_markdown(merged, meta)
    assert "[01:05]" in md


def test_resolve_audio_input_absolute_path(transcribe_module, tmp_path):
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake audio")
    path, name = transcribe_module._resolve_audio_input(str(audio))
    assert path == audio.resolve()
    assert name == "test.wav"


def test_resolve_audio_input_missing_path(transcribe_module):
    path, err = transcribe_module._resolve_audio_input("/nonexistent/foo.wav")
    assert path is None
    assert "not found" in err
