"""S31: Video generation MCP health (MLX-native LTX-2.3 via video_mlx).

The `video` M7 module is off by default, so an absent video_mlx MCP is INFO,
not a failure — enable with `./launch.sh install-video-mlx` + `portal module
enable video`.
"""

import time

from tests.acceptance._common import (
    MCP,
    _get,
    record,
)


async def run() -> None:
    """S31: video_mlx MCP health."""
    print("\n━━━ S31. VIDEO GENERATION ━━━")
    sec = "S31"

    t0 = time.time()
    code, _ = await _get(f"http://localhost:{MCP['video_mlx']}/health")
    record(
        sec,
        "S31-01",
        "video-mlx MCP health (optional)",
        "PASS" if code == 200 else "INFO",
        f"HTTP {code}",
        t0=t0,
    )
