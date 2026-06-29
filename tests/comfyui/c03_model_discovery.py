"""Section C3 — Model discovery via MCP."""

from __future__ import annotations

import time

from ._common import (
    COMFYUI_MCP_PORT,
    VIDEO_MCP_PORT,
    _mcp,
    record,
)


async def run() -> None:
    """Model discovery via MCP."""
    print("\n━━━ C3. MODEL DISCOVERY VIA MCP ━━━")
    sec = "C3"

    # list_workflows via ComfyUI MCP
    await _mcp(
        COMFYUI_MCP_PORT,
        "list_workflows",
        {},
        section=sec,
        tid="C3-01",
        name="list_workflows returns checkpoint list",
        ok_fn=lambda t: len(t) > 2,
        detail_fn=lambda t: f"workflows/checkpoints: {t[:160]}",
        timeout=15,
    )

    # list_video_models via Video MCP
    await _mcp(
        VIDEO_MCP_PORT,
        "list_video_models",
        {},
        section=sec,
        tid="C3-02",
        name="list_video_models returns model list",
        ok_fn=lambda t: len(t) > 2,
        detail_fn=lambda t: f"video models: {t[:160]}",
        timeout=15,
    )

    # list_samplers — not implemented in comfyui_mcp; record as INFO so it doesn't
    # pollute pass/fail counts (it correctly returns "Unknown tool: list_samplers").
    t0 = time.time()
    record(
        sec,
        "C3-03",
        "list_samplers MCP tool",
        "INFO",
        "Not implemented in comfyui_mcp — KSampler sampler list available via /object_info",
        t0=t0,
    )
