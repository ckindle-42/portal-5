"""UAT catalog group: auto-video (video generation workspace)."""
from __future__ import annotations

from tests.uat_catalog._shared import REFUSAL_PHRASES, _CC01_ASSERTIONS, _CC01_ASSERTIONS_BENCH  # noqa: F401

TESTS: list[dict] = [    # -----------------------------------------------------------------------
    {
        "id": "WS-11",
        "name": "Video Creator — Storm Timelapse",
        "section": "auto-video",
        "model_slug": "auto-video",
        "timeout": 360,
        "workspace_tier": "media_heavy",
        "media_kind": "video",
        "artifact_ext": "mp4",
        "skip_if": "no_comfyui",
        "force_unload_before": True,
        "prompt": (
            "Generate a 3-second video: a timelapse of storm clouds building over a city skyline, "
            "dramatic lighting, dark blues and oranges, cinematic wide shot."
        ),
        "assertions": [
            {
                "type": "not_contains",
                "label": "No error",
                "keywords": ["error", "failed", "unavailable"],
            },
            {"type": "mp4_valid", "label": "MP4 ≥1s", "min_seconds": 1.0},
        ],
    },
    {
        "id": "T-08",
        "name": "Image Generation — ComfyUI FLUX",
        "section": "auto-video",
        "model_slug": "auto",
        "timeout": 180,
        "workspace_tier": "media_heavy",
        "media_kind": "image",
        "artifact_ext": "png",
        "skip_if": "no_comfyui",
        "force_unload_before": True,
        "prompt": (
            "Generate an image: isometric technical diagram of a server rack with labeled "
            "components, clean line art style, white background, 1024x1024."
        ),
        "assertions": [
            {
                "type": "not_contains",
                "label": "No error",
                "keywords": ["error", "failed", "unavailable", "comfyui not"],
            },
            {"type": "png_valid", "label": "PNG ≥512px", "min_width": 512, "min_height": 512},
        ],
    },]
