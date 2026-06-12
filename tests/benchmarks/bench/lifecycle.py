"""Backend health checks, warmup/unload, and Metal memory lifecycle.

Extracted byte-for-byte from tests/benchmarks/bench_tps.py. Delegates
drain logic to tests.memory_guard exactly as before.
"""

import platform
import subprocess
import sys
import time

import httpx

from tests.memory_guard import memory_pct as _memory_pct_mg
from tests.memory_guard import wait_for_drain as _wait_for_drain_mg

from .config import OLLAMA_URL, PIPELINE_API_KEY, PIPELINE_URL


def _check_backend(url: str, path: str) -> bool:
    headers: dict[str, str] = {}
    if url == PIPELINE_URL and PIPELINE_API_KEY:
        headers["Authorization"] = f"Bearer {PIPELINE_API_KEY}"
    try:
        r = httpx.get(f"{url}{path}", timeout=3.0, headers=headers)
        return r.status_code == 200
    except Exception:
        pass
    return False


def _get_hardware_info() -> dict:
    info: dict = {"platform": platform.system(), "machine": platform.machine()}
    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            info["unified_memory_gb"] = round(int(out.strip()) / 1024**3, 1)
        except Exception:
            pass
        try:
            out = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True)
            info["cpu"] = out.strip()
        except Exception:
            pass
    return info


def _unload_ollama_model(model: str) -> None:
    """Send keep_alive=0 to an Ollama model to force memory reclamation.

    Uses keep_alive=0 with an empty prompt to force immediate unload.
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": model, "keep_alive": 0, "prompt": ""},
            )
    except Exception:
        pass


def _unload_all_running_ollama_models() -> None:
    """Evict every model currently loaded in Ollama via keep_alive=0.

    Uses /api/ps (running models
    only) rather than /api/tags (all installed) to avoid briefly loading models
    that happen to be installed but idle.
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{OLLAMA_URL}/api/ps")
            if r.status_code != 200:
                return
            models = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return
    for name in models:
        try:
            with httpx.Client(timeout=15.0) as client:
                client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={"model": name, "keep_alive": 0, "prompt": ""},
                )
        except Exception:
            pass


def _warmup_ollama_model(model: str) -> bool:
    """Send a minimal warm-up request to force Ollama to load the model.

    Ollama lazily loads models into unified memory on first request. Without
    warm-up, run 1 of every benchmarked model includes load time, inflating
    elapsed and depressing TPS.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "max_tokens": 1,
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{OLLAMA_URL}/v1/chat/completions", json=payload)
            return resp.status_code == 200
    except Exception:
        return False


def _wait_ollama_idle(timeout_s: float = 60.0) -> bool:
    """Poll /api/ps until no models are running (memory fully reclaimed).

    Returns True if Ollama becomes idle within timeout_s, False otherwise.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.get(f"{OLLAMA_URL}/api/ps", timeout=5.0)
            if r.status_code == 200 and not r.json().get("models"):
                return True
        except Exception:
            pass
        time.sleep(2.0)
    return False


def _check_memory_pressure(threshold_pct: float = 85.0) -> tuple[bool, float]:
    """Check current memory pressure. Returns (safe, used_pct)."""
    used = _memory_pct_mg()
    return used < threshold_pct, used


def _wait_metal_drain(
    threshold_pct: float = 80.0, timeout_s: float = 30.0, retries: int = 2
) -> bool:
    """Wait for Metal drain with retry+recovery. See tests/memory_guard.py."""
    return _wait_for_drain_mg(
        threshold_pct=threshold_pct,
        timeout_s=timeout_s,
        poll_s=5.0,
        retries=retries,
        label="bench",
        ollama_url=OLLAMA_URL,
    )


def _cleanup_all_backends() -> None:
    """Full cleanup: unload all Ollama models to free memory.

    Called at the end of the benchmark to prevent OOM after testing completes.
    """
    print("\n  Cleaning up: unloading all models from memory ...", end=" ", flush=True)
    _unload_all_running_ollama_models()
    _wait_ollama_idle(timeout_s=30.0)
    print("ok")
