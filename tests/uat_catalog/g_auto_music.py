"""UAT catalog group: auto-music (music generation workspace)."""
from __future__ import annotations

from tests.uat_catalog._shared import REFUSAL_PHRASES, _CC01_ASSERTIONS, _CC01_ASSERTIONS_BENCH  # noqa: F401

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "WS-12",
        "name": "Music Producer — Dark Ambient Generation",
        "section": "auto-music",
        "model_slug": "auto-music",
        "timeout": 180,
        "workspace_tier": "media_heavy",
        "media_kind": "sound",
        "artifact_ext": "wav",
        "force_unload_before": True,
        "prompt": (
            "Generate a 20-second piece: dark ambient electronic, cinematic tension, "
            "slow evolving pads, subtle percussion, minor key, suitable for a suspense scene."
        ),
        "assertions": [
            {
                "type": "not_contains",
                "label": "No error",
                "keywords": ["error", "failed", "unavailable"],
            },
            {"type": "wav_valid", "label": "WAV ≥5s", "min_seconds": 5.0},
        ],
    },
    {
        "id": "T-09",
        "name": "TTS — British Male Voice",
        "section": "auto-music",
        "model_slug": "auto-music",
        "timeout": 120,
        "workspace_tier": "media_heavy",
        "media_kind": "voice",
        "artifact_ext": "wav",
        "force_unload_before": True,
        "prompt": (
            "Read the following text aloud using a British male voice (bm_george): "
            '"Portal 5 operates entirely on local hardware. Your data never leaves your machine. '
            'All models run on Apple Silicon using the MLX framework."'
        ),
        "assertions": [
            {
                "type": "not_contains",
                "label": "No error",
                "keywords": ["error", "failed", "unavailable"],
            },
            {"type": "wav_valid", "label": "WAV ≥1.5s", "min_seconds": 1.2},
        ],
    },]
