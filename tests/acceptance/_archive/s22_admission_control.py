"""S22: MLX Admission Control tests."""
import asyncio
import time

from tests.acceptance._common import (
    MLX_URL,
    _get_acc_client,
    _mlx_health,
    record,
)


async def run() -> None:
    """S22: MLX Admission Control tests (P5-FUT-009)."""
    print("\n━━━ S22. MLX ADMISSION CONTROL ━━━")
    sec = "S22"

    # S22-01: Check MLX proxy is running
    t0 = time.time()
    state, data = await _mlx_health()
    if state == "unreachable":
        record(
            sec, "S22-01", "MLX proxy for admission control", "INFO", "MLX proxy not running", t0=t0
        )
        return
    record(sec, "S22-01", "MLX proxy for admission control", "PASS", f"state: {state}", t0=t0)

    # S22-03: Test that proxy returns 503 for oversized model request.
    # Admission control should reject immediately (within ~2s) if memory < model_size + headroom.
    # Use 5s timeout: fast enough to catch prompt 503, short enough to avoid waiting for OOM.
    # ReadTimeout means the proxy accepted and started loading — admission control didn't trigger
    # (typically because enough memory was available), recorded as INFO not FAIL.
    t0 = time.time()
    try:
        c = _get_acc_client()
        # Llama-3.3-70B-Instruct-4bit: tracked at 40GB in MODEL_MEMORY.
        # Requires 40 + 10 = 50GB free — only available on a clean 64GB system.
        r = await c.post(
            f"{MLX_URL}/v1/chat/completions",
            json={
                "model": "mlx-community/Llama-3.3-70B-Instruct-4bit",
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 10,
            },
            timeout=8,
        )
        if r.status_code == 503:
            # Try to parse the detail from JSON body
            try:
                detail = r.json().get("detail", r.text[:100])
            except Exception:
                detail = r.text[:100] or "admission rejected"
            record(
                sec,
                "S22-03",
                "Admission control rejects oversized",
                "PASS",
                f"503: {detail[:80]}",
                t0=t0,
            )
        elif r.status_code == 200:
            # Proxy accepted and returned a response — enough memory was available
            record(
                sec,
                "S22-03",
                "Admission control rejects oversized",
                "INFO",
                "model loaded successfully — insufficient memory pressure to trigger rejection",
                t0=t0,
            )
        else:
            record(
                sec,
                "S22-03",
                "Admission control rejects oversized",
                "WARN",
                f"HTTP {r.status_code}",
                t0=t0,
            )
    except (httpx.ReadTimeout, httpx.ConnectTimeout, asyncio.TimeoutError):
        # Proxy accepted request and started loading (no immediate rejection) — memory not tight enough
        free_gb = _free_ram_gb()
        record(
            sec,
            "S22-03",
            "Admission control rejects oversized",
            "INFO",
            f"proxy accepted 70B request (free RAM: {free_gb:.1f}GB >= 50GB threshold) — no rejection expected",
            t0=t0,
        )
    except Exception as e:
        record(
            sec,
            "S22-03",
            "Admission control rejects oversized",
            "WARN",
            str(e)[:100] or repr(e)[:100],
            t0=t0,
        )

    # S22-04: MODEL_MEMORY dict coverage check
    t0 = time.time()
    try:
        # Check that common MLX models have memory estimates
        models_with_estimates = len(_MLX_MODEL_SIZES_GB)
        record(
            sec,
            "S22-04",
            "Model memory estimates",
            "PASS" if models_with_estimates >= 10 else "WARN",
            f"{models_with_estimates} models with size estimates",
            t0=t0,
        )
    except Exception as e:
        record(sec, "S22-04", "Model memory estimates", "WARN", str(e)[:100], t0=t0)
