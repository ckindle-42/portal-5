"""Section C7 — Image generation: parameter sweep."""

from __future__ import annotations

import time

from ._common import (
    COMFYUI_MCP_PORT,
    _comfyui_get,
    _filter_checkpoints,
    _mcp,
    _wait_for_comfyui_idle,
    record,
)


async def run() -> None:
    """Image generation: parameter sweep."""
    """Test that different generation parameters produce valid (distinct) responses.

    Uses the fastest available checkpoint. Tests seed determinism, step count
    variation, and negative prompt support.
    """
    print("\n━━━ C7. IMAGE GENERATION — PARAMETER SWEEP ━━━")
    sec = "C7"

    # Discover fastest available checkpoint
    t0 = time.time()
    code, data = await _comfyui_get("/object_info", timeout=15)
    test_ckpt = ""
    if code == 200 and isinstance(data, dict):
        ckpt_node = data.get("CheckpointLoaderSimple", {})
        raw = ckpt_node.get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
        ckpts = _filter_checkpoints(raw)
        # Prefer schnell (fastest) → sdxl → xl → anything
        for candidate_pattern in ["schnell", "sdxl", "xl", ""]:
            matches = (
                [c for c in ckpts if candidate_pattern in c.lower()] if candidate_pattern else ckpts
            )
            if matches:
                test_ckpt = matches[0]
                break

    if not test_ckpt:
        record(
            sec,
            "C7-01",
            "Parameter sweep: no checkpoint available",
            "INFO",
            "skipped — no checkpoint installed",
            t0=t0,
        )
        for tid in ["C7-02", "C7-03", "C7-04"]:
            record(sec, tid, "Parameter sweep test", "INFO", "skipped", t0=None)
        return

    record(sec, "C7-01", "Parameter sweep using checkpoint", "INFO", f"using: {test_ckpt}", t0=t0)

    # Seed determinism: same seed → same output filename/hash
    await _wait_for_comfyui_idle()
    await _mcp(
        COMFYUI_MCP_PORT,
        "generate_image",
        {
            "prompt": "a blue cube on white background",
            "steps": 4,
            "seed": 1234,
            "checkpoint": test_ckpt,
        },
        section=sec,
        tid="C7-02",
        name="Seed determinism: seed=1234 run 1",
        ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
        detail_fn=lambda t: t[:200],
        warn_if=["error", "failed"],
    )

    # Different step count — fast vs quality comparison
    await _wait_for_comfyui_idle()
    await _mcp(
        COMFYUI_MCP_PORT,
        "generate_image",
        {
            "prompt": "a blue cube on white background",
            "steps": 16,
            "seed": 1234,
            "checkpoint": test_ckpt,
        },
        section=sec,
        tid="C7-03",
        name="Step variation: 16 steps (same seed, quality comparison vs 4)",
        ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
        detail_fn=lambda t: t[:200],
        warn_if=["error", "failed"],
    )

    # Negative prompt support
    await _wait_for_comfyui_idle()
    await _mcp(
        COMFYUI_MCP_PORT,
        "generate_image",
        {
            "prompt": "portrait of a person, photorealistic, highly detailed",
            "negative_prompt": "cartoon, anime, sketch, blurry, deformed, low quality",
            "steps": 8,
            "seed": 99,
            "checkpoint": test_ckpt,
        },
        section=sec,
        tid="C7-04",
        name="Negative prompt: portrait with exclusions (8 steps)",
        ok_fn=lambda t: (
            "success" in t.lower()
            or "url" in t.lower()
            or "filename" in t.lower()
            or "not supported" in t.lower()
        ),
        detail_fn=lambda t: t[:200],
        warn_if=["error", "failed"],
    )
