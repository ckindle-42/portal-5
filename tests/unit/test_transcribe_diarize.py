"""Unit tests for mlx-transcribe deterministic helpers.

Covers the Parakeet-word / Sortformer-turn merge, run smoothing, markdown
formatting, and file resolution. Model loading and audio I/O are out of scope
(acceptance tests S9-03..05 cover those).
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
    stt_utils = type(sys)("mlx_audio.stt.utils")
    stt_utils.load = lambda *a, **k: None  # type: ignore[attr-defined]
    vad = type(sys)("mlx_audio.vad")
    vad.load = lambda *a, **k: None  # type: ignore[attr-defined]
    sys.modules.setdefault("mlx_audio.stt", stt)
    sys.modules.setdefault("mlx_audio.stt.utils", stt_utils)
    sys.modules.setdefault("mlx_audio.vad", vad)

    spec = importlib.util.spec_from_file_location("mlx_transcribe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _words(*spans: tuple[float, float, str]) -> list[dict]:
    return [{"start": s, "end": e, "text": t} for s, e, t in spans]


# ── _speaker_for_span ─────────────────────────────────────────────────────────


def test_speaker_for_span_picks_max_overlap(transcribe_module):
    diar = [
        {"start": 0.0, "end": 5.0, "speaker": 0},
        {"start": 5.0, "end": 10.0, "speaker": 1},
    ]
    assert transcribe_module._speaker_for_span(diar, 4.0, 4.9) == 0
    assert transcribe_module._speaker_for_span(diar, 5.1, 9.0) == 1
    # straddles the boundary but mostly in speaker 1's turn
    assert transcribe_module._speaker_for_span(diar, 4.8, 6.0) == 1


def test_speaker_for_span_nearest_when_no_overlap(transcribe_module):
    diar = [{"start": 0.0, "end": 2.0, "speaker": 0}, {"start": 8.0, "end": 9.0, "speaker": 1}]
    assert transcribe_module._speaker_for_span(diar, 7.0, 7.5) == 1


def test_speaker_for_span_empty_diar_is_none(transcribe_module):
    assert transcribe_module._speaker_for_span([], 0.0, 1.0) is None


# ── _smooth_speaker_runs ──────────────────────────────────────────────────────


def test_smooth_flips_short_wedge(transcribe_module):
    # a single 0.1s "1" wedged between two runs of "0" is a boundary wobble
    words = _words((0.0, 1.0, "a"), (1.0, 1.1, "b"), (1.1, 3.0, "c"))
    assert transcribe_module._smooth_speaker_runs([0, 1, 0], words) == [0, 0, 0]


def test_smooth_keeps_long_interjection(transcribe_module):
    words = _words((0.0, 1.0, "a"), (1.0, 3.0, "b"), (3.0, 4.0, "c"))
    assert transcribe_module._smooth_speaker_runs([0, 1, 0], words) == [0, 1, 0]


def test_smooth_keeps_real_speaker_change(transcribe_module):
    words = _words((0.0, 2.0, "a"), (2.0, 4.0, "b"))
    assert transcribe_module._smooth_speaker_runs([0, 1], words) == [0, 1]


# ── _merge_words_and_speakers ─────────────────────────────────────────────────


def test_merge_monologue_single_speaker(transcribe_module):
    words = _words((0.0, 1.0, " Hello"), (1.0, 2.0, " world"), (2.0, 3.0, " again"))
    diar = [{"start": 0.0, "end": 3.0, "speaker": 0}]
    segments, count = transcribe_module._merge_words_and_speakers(words, diar, None)
    assert count == 1
    assert len(segments) == 1
    assert segments[0]["speaker"] == "SPEAKER_00"
    assert segments[0]["text"] == "Hello world again"


def test_merge_two_speaker_conversation(transcribe_module):
    words = _words(
        (0.0, 1.0, "Hi"),
        (1.0, 2.0, " there"),
        (2.0, 3.0, " Hello"),
        (3.0, 4.0, " back"),
        (4.0, 5.0, " Bye"),
    )
    diar = [
        {"start": 0.0, "end": 2.0, "speaker": 1},
        {"start": 2.0, "end": 4.0, "speaker": 0},
        {"start": 4.0, "end": 5.0, "speaker": 1},
    ]
    segments, count = transcribe_module._merge_words_and_speakers(words, diar, None)
    assert count == 2
    assert [s["speaker"] for s in segments] == ["SPEAKER_00", "SPEAKER_01", "SPEAKER_00"]
    # renumbered by first appearance: raw speaker 1 spoke first -> SPEAKER_00
    assert segments[0]["text"] == "Hi there"
    assert segments[1]["text"] == "Hello back"


def test_merge_punctuation_pinned_to_previous_speaker(transcribe_module):
    # "?" is timestamped just inside speaker 1's turn but belongs to the question
    words = _words((0.0, 1.4, "How are you"), (1.4, 1.5, "?"), (1.5, 3.0, " Good"))
    diar = [{"start": 0.0, "end": 1.45, "speaker": 0}, {"start": 1.45, "end": 3.0, "speaker": 1}]
    segments, _ = transcribe_module._merge_words_and_speakers(words, diar, None)
    assert segments[0]["text"] == "How are you?"
    assert segments[1]["text"] == "Good"


def test_merge_num_speakers_caps_over_segmentation(transcribe_module):
    words = _words((0.0, 3.0, " aaa"), (3.0, 6.0, " bbb"), (6.0, 6.3, " x"), (6.3, 9.0, " ccc"))
    diar = [
        {"start": 0.0, "end": 3.0, "speaker": 0},
        {"start": 3.0, "end": 6.0, "speaker": 1},
        {"start": 6.0, "end": 6.3, "speaker": 2},  # blip
        {"start": 6.3, "end": 9.0, "speaker": 0},
    ]
    _, count = transcribe_module._merge_words_and_speakers(words, diar, num_speakers=2)
    assert count == 2


def test_merge_no_diarization_all_one_speaker(transcribe_module):
    words = _words((0.0, 1.0, "a"), (1.0, 2.0, " b"))
    segments, count = transcribe_module._merge_words_and_speakers(words, [], None)
    assert count == 1
    assert all(s["speaker"] == "SPEAKER_00" for s in segments)


def test_merge_empty_words(transcribe_module):
    assert transcribe_module._merge_words_and_speakers([], [], None) == ([], 0)


# ── markdown + file resolution (unchanged behaviour) ──────────────────────────


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


def test_resolve_audio_input_unknown_id_errors_instead_of_latest_upload(
    transcribe_module, tmp_path, monkeypatch
):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads" / "abc-123_meeting.wav").write_bytes(b"fake audio")
    path, err = transcribe_module._resolve_audio_input("no-such-file-id")
    assert path is None
    assert "file not found" in err


@pytest.fixture()
def upload_workspace(tmp_path, monkeypatch):
    """Two uploads: the named one (abc-123) older than the other (def-456)."""
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    named = uploads / "abc-123_meeting.wav"
    latest = uploads / "def-456_other.wav"
    named.write_bytes(b"fake audio")
    latest.write_bytes(b"fake audio")
    return uploads


def test_resolve_audio_input_empty_id_errors_instead_of_latest_upload(
    transcribe_module, upload_workspace
):
    for empty in ("", "   "):
        path, err = transcribe_module._resolve_audio_input(empty)
        assert path is None
        assert "file not found" in err
        assert "def-456" not in err


def test_resolve_audio_input_omitted_still_auto_detects(transcribe_module, upload_workspace):
    path, name = transcribe_module._resolve_audio_input(None)
    assert path == (upload_workspace / "def-456_other.wav").resolve()
    assert name == "def-456_other.wav"


def test_resolve_audio_input_valid_id_resolves_that_file(transcribe_module, upload_workspace):
    path, name = transcribe_module._resolve_audio_input("abc-123")
    assert path == (upload_workspace / "abc-123_meeting.wav").resolve()
    assert name == "abc-123_meeting.wav"


def test_transcribe_tools_return_error_for_empty_id(transcribe_module, upload_workspace):
    import asyncio

    plain = asyncio.run(transcribe_module.transcribe_audio(file=""))
    diarized = asyncio.run(transcribe_module.transcribe_with_speakers(file=""))
    assert "file not found" in plain["error"]
    assert "file not found" in diarized["error"]


# ── whisper MCP (:8915) mirrors the same guard ────────────────────────────────


@pytest.fixture()
def whisper_module(monkeypatch):
    pytest.importorskip("mcp")
    from portal.modules.media.tools import whisper_mcp

    calls: list[tuple[str, dict]] = []

    async def fake_host(tool: str, arguments: dict) -> dict:
        calls.append((tool, arguments))
        return {"text": arguments.get("file", "auto-detected")}

    monkeypatch.setattr(whisper_mcp, "_try_host", fake_host)
    return whisper_mcp, calls


def test_whisper_empty_file_errors_without_calling_the_host(whisper_module):
    import asyncio

    whisper, calls = whisper_module
    plain = asyncio.run(whisper.transcribe_audio(file_path=""))
    diarized = asyncio.run(whisper.transcribe_with_speakers(file=""))
    assert "file not found" in plain["error"]
    assert "file not found" in diarized["error"]
    assert calls == []


def test_whisper_omitted_file_still_auto_detects(whisper_module):
    import asyncio

    whisper, calls = whisper_module
    assert asyncio.run(whisper.transcribe_audio())["text"] == "auto-detected"
    assert calls == [("transcribe_audio", {})]


def test_whisper_named_file_is_forwarded_not_replaced_by_latest(whisper_module):
    import asyncio

    whisper, _calls = whisper_module
    assert asyncio.run(whisper.transcribe_audio(file_path="abc-123"))["text"] == "abc-123"
