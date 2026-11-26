"""Explicit side-effect intent for media tools (release_1_0 QAT Stage 2).

s2-p6-auto-audio::music and s2-p6-voice-clone answered in prose on 8B seats, and
s2-p6-auto-audio::video called video_models instead of video_start. The office/code
matcher had no media entries; these pin the single media tool only on an explicit request.
"""

from __future__ import annotations

import pytest

from portal.platform.inference.router_pipe import (
    _select_explicit_required_tool,
    _select_explicit_required_tools,
)

MEDIA_TOOLS = {
    "music_start",
    "clone_voice",
    "video_start",
    "transcribe_audio",
    "video_models",
    "music_models",
    "list_voices",
}


def _select(prompt: str, tools: set[str] | None = None) -> str | None:
    return _select_explicit_required_tool(
        [{"role": "user", "content": prompt}], MEDIA_TOOLS if tools is None else tools
    )


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Generate a 10-second ambient synthwave music track", "music_start"),
        ("Compose a 10-second lo-fi loop.", "music_start"),
        ("compose a song about the sea", "music_start"),
        ("make a beat", "music_start"),
        ("generate an audio clip of rain", "music_start"),
        ("generate an instrumental clip", "music_start"),
        ("Clone the uploaded reference voice and say hello", "clone_voice"),
        ("voice clone of my uploaded sample", "clone_voice"),
        ("use clone_voice on the reference audio", "clone_voice"),
        ("Generate a short 3-second video of ocean waves", "video_start"),
        ("render a clip of the logo spinning", "video_start"),
        ("create an animation of a bouncing ball", "video_start"),
        ("make an mp4 of the slideshow", "video_start"),
        # A voice-clone request is not also a music request (brief: AND NOT voice cloning).
        ("clone my voice and generate a song", "clone_voice"),
    ],
)
def test_explicit_media_requests_pin_one_tool(prompt: str, expected: str) -> None:
    assert _select(prompt) == expected


@pytest.mark.parametrize(
    "prompt",
    [
        "list available video models",
        "what video models exist?",
        "how does voice cloning work?",
        "How do I generate a music track?",
        "Can you explain how to clone a voice?",
        "I'll clone the voice myself",
        "show me how to render a video",
    ],
)
def test_questions_and_lookups_stay_on_auto(prompt: str) -> None:
    assert _select(prompt) is None


@pytest.mark.parametrize(
    "prompt",
    [
        "generate a song and a video",
        "make a music video",
    ],
)
def test_ambiguous_media_requests_stay_on_auto(prompt: str) -> None:
    assert _select(prompt) is None


def test_media_tool_must_be_in_the_whitelist() -> None:
    assert _select("Generate a short video of ocean waves", {"music_start"}) is None
    assert _select("Clone the uploaded reference voice", {"music_start"}) is None
    assert _select("Generate a music track", {"create_excel", "execute_python"}) is None


def test_actual_qat_stage2_media_prompts_pin_their_tool() -> None:
    # Verbatim prompts from tests/qat/scenarios.py (s2-p6 media_heavy + voice-clone).
    assert _select("Compose a 10-second lo-fi loop.") == "music_start"
    assert _select("Generate a 4-second MP4 of ocean waves.") == "video_start"
    assert (
        _select(
            "Clone a voice from the attached audio clip with clone_voice and have it say: "
            "Portal five voice clone parity verified. Surface the download link for the "
            "generated audio."
        )
        == "clone_voice"
    )


def test_music_generation_beats_transcription_on_actual_workspace_tools() -> None:
    prompt = "Compose a 10-second lo-fi loop."
    assert _select(prompt, {"music_start", "music_status", "transcribe_audio"}) == "music_start"


def test_stage5_named_music_tool_stays_selected_over_transcription() -> None:
    prompt = (
        "Use music_start to compose an instrumental lo-fi music loop in WAV format, "
        "at least ten seconds long, with a clear melody and soft percussion. Return the WAV link."
    )
    assert _select_explicit_required_tools(
        [{"role": "user", "content": prompt}],
        {"music_start", "music_status", "transcribe_audio"},
    ) == ["music_start"]
