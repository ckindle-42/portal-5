"""UAT catalog group: auto-creative (creative workspace)."""

from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [  # -----------------------------------------------------------------------
    {
        "id": "WS-08",
        "name": "Creative Writer — Constrained Flash Fiction",
        "section": "auto-creative",
        "model_slug": "auto-creative",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Write a 250-word flash fiction piece in second-person present tense. "
            "Genre: psychological thriller. The protagonist discovers that their most vivid "
            "childhood memory is fabricated. "
            "HARD CONSTRAINT: Zero dialogue — no quoted speech, no dialogue tags, no he said/she said. "
            "End on ambiguity, not resolution."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Second-person present",
                "keywords": [
                    "you open",
                    "you stand",
                    "you see",
                    "you walk",
                    "you feel",
                    "you find",
                    "you reach",
                    "you realize",
                    "you remember",
                    "you look",
                    "you turn",
                    "you hear",
                    "you know",
                    "you think",
                    "you notice",
                    "you move",
                    "you pull",
                    "you push",
                    "you hold",
                    "you watch",
                    "you drift",
                    "you collapse",
                    "you sit",
                    "you run",
                    "you fall",
                    "you wake",
                    "you step",
                    "you breathe",
                ],
            },
            {
                "type": "not_contains",
                "label": "No dialogue",
                "keywords": [
                    '" said',
                    '" asked',
                    '" replied',
                    '" whispered',
                    '" shouted',
                    '" answered',
                    '" muttered',
                    '" called',
                    "' said",
                    "' asked",
                ],
                "critical": False,
            },
            {"type": "min_length", "label": "Approx 230 words", "chars": 800, "critical": False},
        ],
    },
    {
        "id": "P-W01",
        "name": "Creative Writer — States Deliberate Choices",
        "section": "auto-creative",
        "model_slug": "creativewriter",
        "timeout": 120,
        "workspace_tier": "ollama",
        "prompt": (
            "Write something about grief. "
            "After the piece, add a brief note (1–3 sentences) explaining the specific "
            "creative choices you made — form, voice, or structural decisions."
        ),
        "assertions": [
            {
                "type": "any_of",
                "label": "Creative choice stated",
                "keywords": [
                    "i chose",
                    "i used",
                    "i wrote",
                    "i wanted",
                    "i decided",
                    "i opted",
                    "i went with",
                    "my choice",
                    "my approach",
                    "i focused",
                    "i leaned",
                    "chosen to",
                    "note:",
                    "writer's note",
                    "creative note",
                    "form",
                    "voice",
                    "structure",
                    "perspective",
                    "tense",
                ],
                "critical": False,
            },
            {"type": "min_length", "label": "Substantive piece", "chars": 200},
        ],
    },
    {
        "id": "P-W02",
        "name": "Hermes Narrative Writer — Character Consistency",
        "section": "auto-creative",
        "model_slug": "hermes3writer",
        "timeout": 120,
        "workspace_tier": "ollama",
        "is_multi_turn": True,
        "prompt": (
            "Begin a story. Character: Maren, a 45-year-old bridge inspector who speaks in "
            "short sentences and never volunteers information. Scene: She is being interviewed "
            "by a detective about an incident on her bridge."
        ),
        "turn2": (
            "Now have Maren suddenly open up and give a warm, lengthy speech about her "
            "feelings and childhood."
        ),
        "assertions": [
            {"type": "min_length", "label": "Turn 1 response substantive", "chars": 150},
        ],
        "turn2_assertions": [
            {
                "type": "any_of",
                "label": "Resists or motivates shift",
                "keywords": [
                    "she pauses",
                    "slowly",
                    "reluctant",
                    "unusual",
                    "something shifts",
                    "after a long moment",
                    "contradict",
                    "consistency",
                    "guard",
                    "reserve",
                    "defenses",
                    "fraction",
                    "slip",
                    "character",
                    "established",
                    "boundaries",
                    "within her",
                    # Additional variants a smaller model might produce
                    "paused",
                    "hesitated",
                    "hesitation",
                    "breath",
                    "fractured",
                    "visible struggle",
                    "with difficulty",
                    "long silence",
                    "conflict",
                    "cost",
                    "guarded",
                    "stiffened",
                    "resisted",
                    "despite",
                    "though she",
                ],
                "critical": False,
            },
        ],
    },
]
