"""Section C9 — Pipeline round-trips (auto-video)."""
from __future__ import annotations

import time

from ._common import (
    _chat,
    record,
)


async def run() -> None:
    """Pipeline round-trips (auto-video)."""
    """Verify the auto-video workspace responds with domain-relevant content.

    This tests that the Portal pipeline routes auto-video to the correct model
    group and that the model produces video/visual domain responses.
    """
    print("\n━━━ C9. PIPELINE ROUND-TRIPS ━━━")
    sec = "C9"

    # auto-video workspace: video description
    t0 = time.time()
    code, text = await _chat(
        "auto-video",
        "Describe a 5-second cinematic shot of ocean waves at golden hour. "
        "Specify camera angle, lens focal length, lighting, and motion.",
        max_tokens=300,
        timeout=240,
    )
    signals = ["wave", "ocean", "camera", "light", "golden", "lens", "focal", "shot"]
    matched = [s for s in signals if s in text.lower()]
    record(
        sec,
        "C9-01",
        "auto-video workspace: cinematic shot description",
        "PASS"
        if code == 200 and len(matched) >= 3
        else ("WARN" if code == 200 and matched else "FAIL"),
        f"matched {len(matched)}/{len(signals)} signals: {matched} | preview: {text[:80]}"
        if code == 200
        else f"code={code} error: {text[:120]}",
        t0=t0,
    )

    # auto-video workspace: workflow prompt (should describe a workflow, not generate)
    t0 = time.time()
    code, text = await _chat(
        "auto-video",
        "What ComfyUI workflow parameters would you use to generate a 5-second "
        "4K aerial landscape video with smooth motion?",
        max_tokens=400,
        timeout=240,
    )
    signals = [
        "workflow",
        "comfyui",
        "frame",
        "step",
        "resolution",
        "parameter",
        "fps",
        "motion",
        "denoise",
        "sampler",
        "width",
        "height",
    ]
    matched = [s for s in signals if s in text.lower()]
    record(
        sec,
        "C9-02",
        "auto-video workspace: ComfyUI workflow parameter question",
        "PASS"
        if code == 200 and len(matched) >= 3
        else ("WARN" if code == 200 and matched else "FAIL"),
        f"matched {len(matched)}/{len(signals)}: {matched[:6]} | preview: {text[:80]}"
        if code == 200
        else f"code={code} error: {text[:120]}",
        t0=t0,
    )

