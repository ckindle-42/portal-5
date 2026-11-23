"""Explicit side-effect intent for media tools (release_1_0 QAT Stage 2).

s2-p6-auto-audio::music and s2-p6-voice-clone answered in prose on 8B seats, and
s2-p6-auto-audio::video called video_models instead of generate_video. The office/code
matcher had no media entries; these pin the single media tool only on an explicit request.
"""

from __future__ import annotations

import pytest

from portal.platform.inference.router.tools import _select_explicit_required_tool

MEDIA_TOOLS = {
    "generate_music",
    "clone_voice",
    "generate_video",
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
        ("Generate a 10-second ambient synthwave music track", "generate_music"),
        ("compose a song about the sea", "generate_music"),
        ("make a beat", "generate_music"),
        ("generate an audio clip of rain", "generate_music"),
        ("generate an instrumental clip", "generate_music"),
        ("Clone the uploaded reference voice and say hello", "clone_voice"),
        ("voice clone of my uploaded sample", "clone_voice"),
        ("use clone_voice on the reference audio", "clone_voice"),
        ("Generate a short 3-second video of ocean waves", "generate_video"),
        ("render a clip of the logo spinning", "generate_video"),
        ("create an animation of a bouncing ball", "generate_video"),
        ("make an mp4 of the slideshow", "generate_video"),
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
    assert _select("Generate a short video of ocean waves", {"generate_music"}) is None
    assert _select("Clone the uploaded reference voice", {"generate_music"}) is None
    assert _select("Generate a music track", {"create_excel", "execute_python"}) is None
