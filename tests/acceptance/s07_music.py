"""S7: Music generation tests."""
import time

from tests.acceptance._common import (
    MCP,
    _get,
    _mcp,
    record,
)


async def run() -> None:
    """S7: Music generation tests."""
    print("\n━━━ S7. MUSIC GENERATION ━━━")
    sec = "S7"

    # S7-01: Music MCP health
    t0 = time.time()
    code, data = await _get(f"http://localhost:{MCP['music']}/health")
    if code == 200 and isinstance(data, dict):
        record(
            sec,
            "S7-01",
            "Music MCP health",
            "PASS",
            f"service: {data.get('service', 'unknown')}",
            t0=t0,
        )
    else:
        record(sec, "S7-01", "Music MCP health", "WARN", f"HTTP {code}", t0=t0)

    # S7-02: Generate music
    await _mcp(
        MCP["music"],
        "generate_music",
        {
            "prompt": "upbeat jazz piano solo",
            "duration": 5,
            "model_size": "small",
        },
        section=sec,
        tid="S7-02",
        name="Generate music (5s jazz)",
        ok_fn=lambda t: "success" in t.lower() or "path" in t.lower() or "wav" in t.lower(),
        warn_if=["not available", "error"],
        timeout=180,
    )
