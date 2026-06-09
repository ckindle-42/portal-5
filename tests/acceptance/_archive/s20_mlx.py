"""S20: MLX acceleration tests."""
import time
from tests.acceptance._common import (
    MLX_URL,
    record,
    _get,
    _mlx_health,
)

async def run() -> None:
    """S20: MLX acceleration tests."""
    print("\n━━━ S20. MLX ACCELERATION ━━━")
    sec = "S20"

    # S20-01: MLX proxy health
    t0 = time.time()
    state, data = await _mlx_health()
    record(
        sec,
        "S20-01",
        "MLX proxy health",
        "PASS" if state in ("ready", "none", "switching") else "WARN",
        f"state: {state}, data: {str(data)[:80]}",
        t0=t0,
    )

    # S20-02: MLX /v1/models endpoint
    t0 = time.time()
    code, data = await _get(f"{MLX_URL}/v1/models")
    if code == 200 and isinstance(data, dict):
        models = data.get("data", [])
        record(sec, "S20-02", "MLX /v1/models", "PASS", f"{len(models)} models", t0=t0)
    elif code == 503:
        record(sec, "S20-02", "MLX /v1/models", "INFO", "503 (no model loaded)", t0=t0)
    else:
        record(sec, "S20-02", "MLX /v1/models", "WARN", f"HTTP {code}", t0=t0)

    # S20-03: Memory info endpoint
    t0 = time.time()
    code, data = await _get(f"{MLX_URL}/health/memory")
    if code == 200:
        record(sec, "S20-03", "MLX memory info", "PASS", str(data)[:100], t0=t0)
    else:
        record(sec, "S20-03", "MLX memory info", "INFO", f"HTTP {code}", t0=t0)
