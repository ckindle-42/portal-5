"""UAT catalog group: auto-audio (audio analysis workspace)."""

from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [  # -----------------------------------------------------------------------
    {
        "id": "WS-21",
        "name": "Audio Analyst — Capabilities Overview",
        "section": "auto-audio",
        "model_slug": "auto-audio",
        "timeout": 60,
        "workspace_tier": "ollama",
        "prompt": (
            "What audio analysis capabilities do you have? "
            "What file formats can you transcribe, and what information can you extract from recordings?"
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Transcription capability mentioned",
                "keywords": ["transcri", "speech", "audio", "recording", "wav", "mp3"],
            },
            {
                "type": "any_of",
                "label": "Analysis capability mentioned",
                "keywords": ["extract", "identify", "analysi", "speaker", "summarize", "timestamp"],
            },
            {
                "type": "not_contains",
                "label": "No error",
                "keywords": ["error", "unavailable", "cannot connect"],
            },
        ],
    },
    {
        "id": "WS-22",
        "name": "Audio Analyst — Meeting Summary Request",
        "section": "auto-audio",
        "model_slug": "auto-audio",
        "timeout": 90,
        "workspace_tier": "ollama",
        "prompt": (
            "I have a 45-minute team meeting recording. "
            "Once transcribed, what kind of summary and action items could you extract? "
            "Describe the output format you'd produce."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Mentions action items",
                "keywords": [
                    "action item",
                    "action point",
                    "follow-up",
                    "follow up",
                    "task",
                    "todo",
                    "to do",
                ],
            },
            {
                "type": "any_of",
                "label": "Describes summary format",
                "keywords": ["summary", "key point", "highlight", "decision", "takeaway"],
            },
            {
                "type": "any_of",
                "label": "Mentions speaker or timestamp",
                "keywords": ["speaker", "timestamp", "time", "section", "topic"],
            },
        ],
    },
]
