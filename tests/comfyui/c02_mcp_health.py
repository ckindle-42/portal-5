"""Section C2 — MCP bridge health (comfyui_mcp, video_mcp)."""
from __future__ import annotations

import httpx
import json
import subprocess
import time

from ._common import (
    COMFYUI_MCP_PORT,
    DC,
    VIDEO_MCP_PORT,
    record,
)


async def run() -> None:
    """MCP bridge health (comfyui_mcp, video_mcp)."""
    print("\n━━━ C2. MCP BRIDGE HEALTH ━━━")
    sec = "C2"

    for tid, port, name in [
        ("C2-01", COMFYUI_MCP_PORT, "ComfyUI MCP bridge"),
        ("C2-02", VIDEO_MCP_PORT, "Video MCP bridge"),
    ]:
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(f"http://localhost:{port}/health")
                record(
                    sec,
                    tid,
                    f"{name} (:{port})",
                    "PASS" if r.status_code == 200 else "WARN",
                    str(r.json()) if r.status_code == 200 else f"HTTP {r.status_code}",
                    t0=t0,
                )
        except Exception as e:
            record(sec, tid, f"{name} (:{port})", "FAIL", str(e)[:120], t0=t0)

    # Docker containers running
    t0 = time.time()
    result = subprocess.run(
        DC + ["ps", "--format", "json"],
        capture_output=True,
        text=True,
    )
    containers: list[str] = []
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                name = obj.get("Name", obj.get("Service", ""))
                if "comfyui" in name.lower() or "video" in name.lower():
                    containers.append(f"{name}={obj.get('State', '?')}")
            except Exception:
                pass
    record(
        sec,
        "C2-03",
        "ComfyUI+video MCP containers running",
        "PASS" if containers else "WARN",
        ", ".join(containers) if containers else "none matched — check docker compose ps",
        t0=t0,
    )

