"""S30: Image + video generation tests (MLX-native — MFLUX / video_mlx)."""

import time

from tests.acceptance._common import (
    MCP,
    _get,
    record,
)


async def run() -> None:
    """S30: MLX-native image/video generation MCP health."""
    print("\n━━━ S30. IMAGE / VIDEO GENERATION ━━━")
    sec = "S30"

    # S30-01: MFLUX image MCP health
    t0 = time.time()
    code, _ = await _get(f"http://localhost:{MCP['mflux']}/health")
    record(
        sec,
        "S30-01",
        "MFLUX image MCP",
        "PASS" if code == 200 else "INFO",
        f"HTTP {code}",
        t0=t0,
    )

    # S30-02: video-mlx MCP health (video module off by default — INFO when absent)
    t0 = time.time()
    code, _ = await _get(f"http://localhost:{MCP['video_mlx']}/health")
    record(
        sec,
        "S30-02",
        "video-mlx MCP (optional)",
        "PASS" if code == 200 else "INFO",
        f"HTTP {code}",
        t0=t0,
    )
