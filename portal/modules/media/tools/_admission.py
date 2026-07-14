"""Cross-engine VRAM/RAM pre-flight admission check for heavy media generation.

Tier 1 of TASK_VRAM_ADMISSION_V1 (Slice 7): a best-effort check that refuses an
oversized job with a structured, actionable error *before* it OOMs the host,
rather than after. This does not replace real cross-engine coordination with
Ollama (that would be Tier 2 — explicitly out of scope, see the task's
[GATE: SCOPE]); it only prevents the specific failure mode observed live during
Slice P media bring-up: loading a large ComfyUI model when too little memory is
free already crashes the box.

No historical per-model GB table exists for ComfyUI/media backends (the retired
MLX-proxy admission gate, commit 91f13a9, only covered the old text/VLM inference
tier). These estimates are session-observed (Slice P, 2026-07-14) and mirrored from
`unit-fact-media-memory-budget` (portal/platform/wiki/adapters/seed_facts.py) — kept
as a separate copy here rather than imported, matching Rule 3 (MCP modules are
independent services, zero cross-imports from platform internals).
"""

from __future__ import annotations

import os

MEDIA_MODEL_MEMORY_GB: dict[str, float] = {
    "comfyui:flux-schnell": 27.2,  # checkpoint 22 + vae 0.32 + clip_l 0.235 + t5xxl_fp8 4.6
    "comfyui:sdxl": 6.5,  # single self-contained checkpoint
    "video:wan21-nsfw": 38.2,  # unet 27 + clip 11 + vae 0.24 (14B — caused the 2026-07-14 lockup)
    "music:small": 2.0,
    "music:medium": 6.0,
    "music:large": 12.0,
}

MEMORY_HEADROOM_GB: float = float(os.environ.get("MEDIA_MEMORY_HEADROOM_GB", "4.0"))
MEMORY_UNKNOWN_DEFAULT_GB: float = float(os.environ.get("MEDIA_MEMORY_UNKNOWN_DEFAULT_GB", "16.0"))


def _free_gb_from_proc_meminfo() -> float | None:
    """Linux (Docker containers): MemAvailable from /proc/meminfo, in GB."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb / 1024 / 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def _free_gb_from_vm_stat() -> float | None:
    """macOS (host-native processes, e.g. music_mcp.py): free pages from vm_stat, in GB."""
    import subprocess

    try:
        out = subprocess.check_output(["vm_stat"], timeout=5).decode()
        page_size = 16384  # Apple Silicon default; vm_stat's header confirms this per-host
        for line in out.splitlines():
            if line.startswith("Pages free:"):
                pages = int(line.split(":")[1].strip().rstrip("."))
                return pages * page_size / 1024 / 1024 / 1024
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    return None


async def _free_gb_from_comfyui(comfyui_url: str) -> float | None:
    """Best signal for comfyui_mcp/video_mcp: ComfyUI itself runs host-native, so its
    own /system_stats reports true host RAM — not the Docker container's cgroup view."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{comfyui_url}/system_stats")
            resp.raise_for_status()
            data = resp.json()
            return data["system"]["ram_free"] / 1024 / 1024 / 1024
    except (httpx.HTTPError, KeyError, ValueError):
        return None


async def free_unified_gb(comfyui_url: str = "") -> float | None:
    """Best-effort free host memory in GB. Returns None if no signal is available
    (callers should fail open — never block a job on an unmeasurable quantity)."""
    if comfyui_url:
        gb = await _free_gb_from_comfyui(comfyui_url)
        if gb is not None:
            return gb
    gb = _free_gb_from_proc_meminfo()
    if gb is not None:
        return gb
    return _free_gb_from_vm_stat()


def estimate_job_gb(model_key: str) -> tuple[float, bool]:
    """(estimated_gb, is_known). Unknown models get MEMORY_UNKNOWN_DEFAULT_GB."""
    if model_key in MEDIA_MODEL_MEMORY_GB:
        return MEDIA_MODEL_MEMORY_GB[model_key], True
    return MEMORY_UNKNOWN_DEFAULT_GB, False


async def admit(model_key: str, comfyui_url: str = "") -> dict | None:
    """Returns None if the job is admitted, or a structured error dict if refused.

    Fails open (returns None / admits) when free memory can't be measured — an
    unmeasurable quantity must never block a job outright.
    """
    if MEMORY_HEADROOM_GB <= 0:
        return None  # operator-disabled (fail-open escape hatch)

    free_gb = await free_unified_gb(comfyui_url)
    if free_gb is None:
        return None  # no signal — fail open rather than block on an unmeasurable quantity

    estimated_gb, is_known = estimate_job_gb(model_key)
    needed_gb = estimated_gb + MEMORY_HEADROOM_GB
    if needed_gb <= free_gb:
        return None

    known_note = "" if is_known else " (unknown model — using a conservative default estimate)"
    return {
        "success": False,
        "error": (
            f"Refused: {model_key} needs ~{estimated_gb:.0f}GB{known_note} "
            f"(+{MEMORY_HEADROOM_GB:.0f}GB headroom), only {free_gb:.1f}GB free. "
            "Stop ComfyUI (launchctl kickstart -k gui/$(id -u)/com.portal5.comfyui) after "
            "unloading any large model, or unload a loaded Ollama model first "
            "(curl localhost:11434/api/ps to check). See unit-HOWTO-media-memory-and-"
            "launch-order for the safe co-residency matrix."
        ),
    }
