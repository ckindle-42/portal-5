"""Unit tests for transcribe_with_speakers logic (TASK-TRANSCRIBE-001).

Covers deterministic in-memory parts: merge, markdown formatting, file
resolution. Model loading and audio I/O are out of scope (covered by
acceptance tests S9-03 / S9-04 / S9-05 with fixtures).
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
    # Stub imports that pull MLX/PyTorch
    sys.modules.setdefault("mlx_whisper", type(sys)("mlx_whisper"))
    sys.modules.setdefault("pyannote", type(sys)("pyannote"))
    sys.modules.setdefault("pyannote.audio", type(sys)("pyannote.audio"))
    sys.modules.setdefault("torch", type(sys)("torch"))

    spec = importlib.util.spec_from_file_location("mlx_transcribe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_merge_no_diarization_falls_back_to_single_speaker(transcribe_module):
    segments = [
        {"start": 0.0, "end": 2.0, "text": "Hello"},
        {"start": 2.0, "end": 4.0, "text": "World"},
    ]
    merged = transcribe_module._merge(segments, [])
    assert len(merged) == 2
    assert all(s["speaker"] == "SPEAKER_00" for s in merged)


def test_merge_assigns_max_overlap_speaker(transcribe_module):
    segments = [
        {"start": 0.0, "end": 5.0, "text": "First turn"},
        {"start": 5.0, "end": 10.0, "text": "Second turn"},
    ]
    turns = [
        {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
        {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01"},
    ]
    merged = transcribe_module._merge(segments, turns)
    assert merged[0]["speaker"] == "SPEAKER_00"
    assert merged[1]["speaker"] == "SPEAKER_01"


def test_merge_collapses_adjacent_same_speaker(transcribe_module):
    segments = [
        {"start": 0.0, "end": 2.0, "text": "Hello"},
        {"start": 2.0, "end": 4.0, "text": "world"},
        {"start": 4.0, "end": 6.0, "text": "again"},
    ]
    turns = [{"start": 0.0, "end": 6.0, "speaker": "SPEAKER_00"}]
    merged = transcribe_module._merge(segments, turns)
    assert len(merged) == 1
    assert merged[0]["text"] == "Hello world again"


def test_merge_handles_partial_overlap(transcribe_module):
    segments = [{"start": 0.0, "end": 4.0, "text": "mostly speaker 0"}]
    turns = [
        {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"},
        {"start": 3.0, "end": 5.0, "speaker": "SPEAKER_01"},
    ]
    merged = transcribe_module._merge(segments, turns)
    assert merged[0]["speaker"] == "SPEAKER_00"


def test_format_markdown_includes_metadata(transcribe_module):
    merged = [
        {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00", "text": "Hello there"},
        {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01", "text": "General Kenobi"},
    ]
    meta = {"duration": 10.0, "language": "en", "speaker_count": 2}
    md = transcribe_module._format_markdown(merged, meta, "audio.wav")
    assert "Transcript: audio.wav" in md
    assert "**Duration**: 10.0s" in md
    assert "**Speakers**: 2" in md
    assert "**SPEAKER_00**" in md
    assert "**SPEAKER_01**" in md


def test_format_markdown_timestamps(transcribe_module):
    merged = [{"start": 65.0, "end": 70.0, "speaker": "SPEAKER_00", "text": "After a minute"}]
    meta = {"duration": 70.0, "language": "en", "speaker_count": 1}
    md = transcribe_module._format_markdown(merged, meta)
    assert "[01:05]" in md


def test_resolve_audio_input_absolute_path(transcribe_module, tmp_path):
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"fake audio")
    path, name = transcribe_module._resolve_audio_input(str(audio))
    assert path is not None
    assert path == audio.resolve()
    assert name == "test.wav"


def test_resolve_audio_input_missing_path(transcribe_module):
    path, err = transcribe_module._resolve_audio_input("/nonexistent/foo.wav")
    assert path is None
    assert "not found" in err
