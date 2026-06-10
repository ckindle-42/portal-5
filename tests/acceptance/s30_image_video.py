"""S30: Image generation tests (ComfyUI/FLUX)."""
import time

from tests.acceptance._common import (
    COMFYUI_URL,
    MCP,
    _get,
    _get_acc_client,
    record,
)


async def run() -> None:
    """S30: Image generation tests (ComfyUI)."""
    print("\n━━━ S30. IMAGE GENERATION ━━━")
    sec = "S30"

    # S30-01: ComfyUI direct health
    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.get(f"{COMFYUI_URL}/system_stats", timeout=10)
        if r.status_code == 200:
            data = r.json()
            version = data.get("system", {}).get("comfyui_version", "unknown")
            record(sec, "S30-01", "ComfyUI direct", "PASS", f"version: {version}", t0=t0)
        else:
            record(sec, "S30-01", "ComfyUI direct", "WARN", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S30-01", "ComfyUI direct", "INFO", f"not running: {str(e)[:50]}", t0=t0)

    # S30-02: ComfyUI MCP health
    t0 = time.time()
    code, _ = await _get(f"http://localhost:{MCP['comfyui']}/health")
    record(
        sec,
        "S30-02",
        "ComfyUI MCP bridge",
        "PASS" if code == 200 else "INFO",
        f"HTTP {code}",
        t0=t0,
    )
