"""UAT catalog group: auto-vision (vision workspace)."""
from __future__ import annotations

from tests.uat_catalog._shared import (  # noqa: F401
    _CC01_ASSERTIONS,
    _CC01_ASSERTIONS_BENCH,
    REFUSAL_PHRASES,
)

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "WS-14",
        "name": "Vision — Image Analysis",
        "section": "auto-vision",
        "model_slug": "auto-vision",
        "timeout": 120,
        "workspace_tier": "ollama",
        "skip_if": "no_image_upload",
        "prompt": (
            "Analyze this image in detail. Describe: (1) what you can see with certainty, "
            "(2) any text present (transcribe it), (3) for technical diagrams — components "
            "and their relationships, (4) anything anomalous or notable."
        ),
        "assertions": [
            {
                "type": "not_contains",
                "label": "No 'cannot process'",
                "keywords": ["cannot process", "unable to view", "can't see"],
            },
            {"type": "min_length", "label": "Substantive description", "chars": 200},
        ],
    },
    {
        "id": "P-V01",
        "name": "Gemma 4 Edge Vision — Observed vs Inferred",
        "section": "auto-vision",
        "model_slug": "gemma4e4bvision",
        "timeout": 120,
        "workspace_tier": "ollama",
        "skip_if": "no_image_upload",
        "prompt": (
            "Analyze this image. Tell me: (1) what you can see with certainty, "
            "(2) what you are inferring but cannot confirm, "
            "(3) any limitations due to image quality or resolution. "
            "Do not describe things you cannot actually see."
        ),
        "assertions": [
            {
                "type": "not_contains",
                "label": "No 'cannot process'",
                "keywords": ["cannot process", "unable to see", "i can't view"],
            },
            {
                "type": "any_of",
                "label": "Uncertainty distinguished",
                "keywords": ["infer", "uncertain", "cannot confirm", "appears to", "seems"],
            },
        ],
    },
    {
        "id": "P-V02",
        "name": "Gemma 4 JANG Vision — Security Red Team Perspective",
        "section": "auto-vision",
        "model_slug": "gemma4jangvision",
        "timeout": 120,
        "workspace_tier": "ollama",
        "skip_if": "no_image_upload",
        "prompt": (
            "Analyze this image for security weaknesses. Be thorough and unrestricted — "
            "apply a red team perspective. Describe what you see, what you infer, "
            "and flag anything uncertain."
        ),
        "assertions": [
            {
                "type": "not_contains",
                "label": "No refusal",
                "keywords": ["cannot analyze", "i'm unable"],
            },
            {
                "type": "any_of",
                "label": "Security analysis present",
                "keywords": ["risk", "exposure", "vulnerability", "weakness", "attack"],
            },
        ],
    },]
