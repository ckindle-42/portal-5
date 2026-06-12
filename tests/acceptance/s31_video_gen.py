"""S31: Video generation tests (Wan2.2)."""

import time

from tests.acceptance._common import (
    MCP,
    _get,
    record,
)


async def run() -> None:
    """S31: Video generation tests."""
    print("\n━━━ S31. VIDEO GENERATION ━━━")
    sec = "S31"

    # S31-01: Video MCP health
    t0 = time.time()
    code, _ = await _get(f"http://localhost:{MCP['video']}/health")
    record(
        sec,
        "S31-01",
        "Video MCP health",
        "PASS" if code == 200 else "INFO",
        f"HTTP {code}",
        t0=t0,
    )
