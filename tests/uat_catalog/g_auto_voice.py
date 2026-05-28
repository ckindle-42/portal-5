"""UAT catalog group: auto-voice (Whisper STT round-trip)."""
from __future__ import annotations

from tests.uat_catalog._shared import REFUSAL_PHRASES, _CC01_ASSERTIONS, _CC01_ASSERTIONS_BENCH  # noqa: F401

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "M-01",
        "name": "Whisper STT — Voice-to-Text Round-Trip",
        "section": "auto-music",
        "model_slug": "auto-music",
        "timeout": 90,
        "workspace_tier": "media_heavy",
        "media_kind": "voice",
        "skip_if": "no_audio_fixture",
        "force_unload_before": True,
        "fixture": "sample.wav",
        "prompt": (
            "I'm uploading an audio file. Please transcribe it using the "
            "Whisper tool and return the text exactly as spoken."
        ),
        "assertions": [
            {
                "type": "not_contains",
                "label": "No tool error",
                "keywords": ["error", "failed", "unavailable", "no audio"],
            },
            {
                "type": "min_length",
                "label": "Transcript length",
                "chars": 20,
                "critical": False,
            },
            {
                "type": "any_of",
                "label": "Transcript matches fixture content",
                "keywords": ["portal", "five", "acceptance", "quick", "brown", "fox"],
            },
        ],
    },]
