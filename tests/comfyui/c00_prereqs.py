"""Section C0 — Prerequisites (memory, deps, ComfyUI process)."""

from __future__ import annotations

import subprocess
import time

import httpx

from ._common import (
    COMFYUI_URL,
    PIPELINE_URL,
    _clear_comfyui_queue,
    _comfyui_get,
    _free_memory_for_comfyui,
    record,
)


async def run() -> None:
    """Prerequisites (memory, deps, ComfyUI process)."""
    print("\n━━━ C0. PREREQUISITES ━━━")
    sec = "C0"

    # Python deps
    t0 = time.time()
    missing = []
    for pkg in ["httpx", "mcp", "yaml"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    record(
        sec,
        "C0-01",
        "Python dependencies available",
        "PASS" if not missing else "FAIL",
        f"missing: {missing}" if missing else "httpx, mcp, yaml all present",
        t0=t0,
    )

    # Pipeline reachable
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{PIPELINE_URL}/health")
            record(
                sec,
                "C0-02",
                f"Portal pipeline reachable ({PIPELINE_URL})",
                "PASS" if r.status_code == 200 else "FAIL",
                f"HTTP {r.status_code}",
                t0=t0,
            )
    except Exception as e:
        record(sec, "C0-02", f"Portal pipeline reachable ({PIPELINE_URL})", "FAIL", str(e), t0=t0)

    # ComfyUI process running
    t0 = time.time()
    result = subprocess.run(
        ["pgrep", "-f", "comfy.*main.py|python.*main.py.*8188"],
        capture_output=True,
        text=True,
    )
    comfyui_process_running = result.returncode == 0
    record(
        sec,
        "C0-03",
        "ComfyUI process running on host",
        "PASS" if comfyui_process_running else "WARN",
        f"PIDs: {result.stdout.strip()}"
        if comfyui_process_running
        else "not found — start: cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188",
        t0=t0,
    )

    # ComfyUI API reachable
    t0 = time.time()
    code, data = await _comfyui_get("/system_stats")
    record(
        sec,
        "C0-04",
        f"ComfyUI API reachable ({COMFYUI_URL})",
        "PASS" if code == 200 else "WARN",
        f"HTTP {code}" + (f" — {str(data)[:80]}" if code != 200 else ""),
        t0=t0,
    )

    # Free unified memory
    print("  ── Freeing unified memory before tests ──")
    await _free_memory_for_comfyui()

    # Clear ComfyUI queue — stuck tasks from previous runs block all generation tests
    await _clear_comfyui_queue()
