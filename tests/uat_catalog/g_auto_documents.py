"""UAT catalog group: auto-documents (Transcript Analyst golden-path chain)."""

from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [  # (transcribe_with_speakers → create_word_document)
    # -----------------------------------------------------------------------
    {
        "id": "TR-01",
        "name": "Transcript Analyst — Diarize + Word Doc (Golden Path)",
        "section": "auto-documents",
        "model_slug": "transcriptanalyst",  # seeded persona preset
        "timeout": 240,  # transcribe 60-130s + docx + gen
        "workspace_tier": "ollama",
        "media_kind": "voice",
        "skip_if": ["no_two_speaker_audio_fixture", "no_transcribe_server"],
        "force_unload_before": True,
        "fixture": "sample_two_speakers.wav",
        "pre_stage_audio": True,
        "prompt": (
            "I just uploaded an audio file. Please transcribe it with 2 speakers, "
            "then create a Word document from the result titled "
            "'Two-Speaker Transcript'."
        ),
        "assertions": [
            {
                "type": "not_contains",
                "label": "No tool error",
                "keywords": ["error", "failed", "unavailable", "no audio file found"],
            },
            {
                "type": "all_of",
                "label": "Diarization produced >=2 speakers (transcribe_with_speakers ran)",
                "keywords": ["SPEAKER_00", "SPEAKER_01"],
                "critical": True,
            },
            {
                "type": "any_of",
                "label": "Response references a .docx artifact (create_word_document ran)",
                "keywords": ["/files/", "/workspace/generated/documents/", "download_url"],
                "critical": True,
            },
            {
                "type": "any_of",
                "label": "Filename pattern is docx",
                "keywords": [".docx"],
                "critical": True,
            },
            {
                "type": "min_length",
                "label": "Transcript body has substance",
                "chars": 50,
                "critical": False,
            },
        ],
    },
]
