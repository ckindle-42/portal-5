"""Portal 5 UAT — model unload, pipeline pre-warm, media-MCP health.

Extracted verbatim from tests/portal5_uat_driver.py (TASK_UAT_MODULARIZE_V1
phase B). Imports memory_pct directly from tests.memory_guard (not via
tests.uat.health) to keep the lifecycle->health edge absent: health imports
unload_all_models from here (A7 cycle break).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import httpx

from tests.memory_guard import memory_pct as _get_memory_pct
from tests.uat.config import OLLAMA_URL


def _wait_for_ollama_ps_empty(timeout_s: float = 30.0, poll_s: float = 1.0) -> bool:
    """Poll /api/ps until all models are unloaded or timeout_s elapses.

    Event-driven: exits as soon as Ollama reports no loaded models.
    Safety net: hard timeout for cases where Ollama hangs on release.
    Returns True when model list is empty, False on timeout.

    This is step 1 of the two-step drain:
      1. /api/ps empty → Ollama confirmed release (this function)
      2. vm_stat below threshold → Metal buffers reclaimed (_wait_for_drain)
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.get(f"{OLLAMA_URL}/api/ps", timeout=3)
            if r.status_code == 200 and not r.json().get("models"):
                return True
        except Exception:
            pass
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(poll_s, remaining))
    return False


def _unload_running_ollama_models() -> None:
    """Unload all running Ollama models via the Ollama API."""
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/ps", timeout=5)
        if r.status_code != 200:
            return
        models = r.json().get("models", [])
        for m in models:
            name = m.get("name") or m.get("model", "")
            if name:
                print(f"  Unloading Ollama model: {name}", flush=True)
                httpx.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={"model": name, "keep_alive": 0},
                    timeout=10,
                )
    except Exception as e:
        print(f"  WARNING: Ollama unload failed: {e}", flush=True)


# Model unload helpers
# ---------------------------------------------------------------------------


def _pipeline_pre_warm(workspace_id: str = "auto") -> None:
    """Send a minimal request through the pipeline to trigger model cold-load.

    Uses the actual workspace_id for this test so the right model is pre-loaded.
    """
    pipeline_url = os.environ.get("PIPELINE_URL", "http://localhost:9099")
    pipeline_key = os.environ.get("PIPELINE_API_KEY", "")
    if not pipeline_key:
        try:
            env_path = Path(__file__).resolve().parents[2] / ".env"
            for _line in env_path.read_text().splitlines():
                if _line.startswith("PIPELINE_API_KEY="):
                    pipeline_key = _line.split("=", 1)[1].strip()
                    break
        except Exception:
            pass
    if not pipeline_key:
        pipeline_key = "portal-pipeline"
    import threading as _threading

    _prewarm_done = _threading.Event()

    def _prewarm_ticker() -> None:
        tick = 0
        while not _prewarm_done.wait(timeout=30):
            tick += 30
            mem = _get_memory_pct()
            print(
                f"  [pre-warm] {tick}s elapsed — mem={mem:.0f}%",
                flush=True,
            )

    ticker = _threading.Thread(target=_prewarm_ticker, daemon=True, name="prewarm-ticker")
    ticker.start()

    try:
        httpx.post(
            f"{pipeline_url}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {pipeline_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": workspace_id,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
                "stream": False,
            },
            timeout=360,
        )
    except Exception:
        pass
    finally:
        _prewarm_done.set()


def unload_all_models() -> None:
    """Unload all running Ollama models and release GPU memory.

    Two-step drain:
      1. Send keep_alive=0 to all loaded models, then poll /api/ps until
         the list is empty (event-driven — exits as soon as Ollama confirms
         release, not after a fixed sleep).
      2. Caller follows with _wait_for_drain() to wait for macOS Metal to
         reclaim wired pages (vm_stat-driven, same event pattern).
    """
    print("  Unloading all Ollama models ...", flush=True)
    _unload_running_ollama_models()
    _wait_for_ollama_ps_empty(timeout_s=30.0)


def _mflux_running() -> bool:
    """Return True if the MFLUX image MCP is reachable on :8933."""
    import os

    try:
        r = httpx.get(
            f"http://localhost:{os.environ.get('MFLUX_MCP_PORT', '8933')}/health", timeout=3
        )
        return r.status_code == 200
    except Exception:
        return False


def cleanup_after_uat() -> None:
    """Full cleanup after all UAT tests complete — prevents OOM post-run."""
    print("\n  Post-UAT cleanup: evicting all models ...", end=" ", flush=True)
    unload_all_models()
    used = _get_memory_pct()
    print(f"ok (mem={used:.0f}%)", flush=True)
