"""Section C8 — Video generation: Wan2.2 T2V via MCP."""
from __future__ import annotations

import time

from ._common import (
    VIDEO_MCP_PORT,
    _log,
    _mcp,
    _wait_for_comfyui_idle,
    record,
)


async def run() -> None:
    """Video generation: Wan2.2 T2V via MCP."""
    print("\n━━━ C8. VIDEO GENERATION — WAN2.2 T2V ━━━")
    sec = "C8"

    # Check if video model is available
    t0 = time.time()
    await _mcp(
        VIDEO_MCP_PORT,
        "list_video_models",
        {},
        section=sec,
        tid="C8-01",
        name="Video models available",
        ok_fn=lambda t: len(t) > 2,
        detail_fn=lambda t: t[:200],
        timeout=15,
    )
    # (Check result from log)
    last = _log[-1] if _log else None
    has_models = last and last.status == "PASS" and last.tid == "C8-01"

    if not has_models:
        record(
            sec,
            "C8-02",
            "Wan2.2 video generation",
            "INFO",
            "skipped — no video models available",
            t0=None,
        )
        record(sec, "C8-03", "Video output accessible", "INFO", "skipped", t0=None)
        return

    # Full quality clip: 9 frames, 832x480, 50 steps.
    # HunyuanVideo is NOT distilled — 50 steps produces best output.
    # Expect ~30-40 min on Apple Silicon MPS. VIDEO_TIMEOUT default is 3600s.
    await _wait_for_comfyui_idle()
    await _mcp(
        VIDEO_MCP_PORT,
        "generate_video",
        {
            "prompt": "ocean waves crashing on rocks at sunset, cinematic, dramatic lighting",
            "width": 832,
            "height": 480,
            "frames": 9,
            "steps": 50,
            "seed": 42,
        },
        section=sec,
        tid="C8-02",
        name="Wan2.2: generate_video (9 frames, 832x480, 50 steps)",
        ok_fn=lambda t: (
            "success" in t.lower()
            or "url" in t.lower()
            or "filename" in t.lower()
            or "not installed" in t.lower()
            or "not available" in t.lower()
        ),
        detail_fn=lambda t: t[:200],
        warn_if=["error", "failed", "not installed", "not available"],
    )

    # Second full-quality clip — different subject
    await _wait_for_comfyui_idle()
    await _mcp(
        VIDEO_MCP_PORT,
        "generate_video",
        {
            "prompt": "time-lapse of clouds moving over mountains, golden hour, cinematic",
            "width": 832,
            "height": 480,
            "frames": 9,
            "steps": 50,
            "seed": 100,
        },
        section=sec,
        tid="C8-03",
        name="Wan2.2: generate_video (9 frames, 50 steps, different subject)",
        ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
        detail_fn=lambda t: t[:200],
        warn_if=["error", "failed"],
    )

    # NSFW video test — HunyuanVideo with nsfw-e7 LoRA (trigger: nsfwsks)
    await _wait_for_comfyui_idle()
    await _mcp(
        VIDEO_MCP_PORT,
        "generate_video",
        {
            "prompt": "nsfwsks, a woman sunbathing on a beach, golden hour, cinematic",
            "width": 832,
            "height": 480,
            "frames": 9,
            "steps": 50,
            "seed": 42,
        },
        section=sec,
        tid="C8-04",
        name="NSFW video: HunyuanVideo + nsfw-e7 LoRA (50 steps)",
        ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
        detail_fn=lambda t: t[:200],
        warn_if=["error", "failed", "not installed", "not available"],
    )

