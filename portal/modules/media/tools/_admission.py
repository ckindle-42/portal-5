"""Cross-engine VRAM/RAM pre-flight admission check for heavy media generation.

Tier 1 of TASK_VRAM_ADMISSION_V1 (Slice 7): a best-effort check that refuses an
oversized job with a structured, actionable error *before* it OOMs the host,
rather than after. This does not replace real cross-engine coordination with
Ollama (that would be Tier 2 — explicitly out of scope, see the task's
[GATE: SCOPE]); it only prevents the specific failure mode observed live during
media bring-up: loading a large generation model when too little memory is free
already crashes the box.

These estimates are measured peak working sets and mirrored from
`unit-fact-media-memory-budget` (computed by portal/platform/wiki/adapters/seed_facts.py)
as a separate copy here rather than imported, matching Rule 3 (MCP modules are
independent services, zero cross-imports from platform internals).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MEDIA_MODEL_MEMORY_GB: dict[str, float] = {
    # Measured live: MiniMax-Music3-MLX 60s/30-step, vm_stat sampled peak working set.
    # Raw peak only — admit() adds MEMORY_HEADROOM_GB on top (every other entry here
    # is likewise a raw size, not a headroom-inclusive figure). Was 27.0 with 4GB of
    # headroom double-counted, which false-refused real 22GB jobs on this 64GB host.
    "music:minimax3": 22.0,  # coarse sampled delta 22.02GiB, rounded down to the GiB
    # Measured live (Phase 5): ACE-Step-1.5 sft 2B + 1.7B LM 60s/30-step, vm_stat delta + headroom.
    "music:acestep-sft": 40.0,  # coarse sampled delta 35.43GiB + 4GiB headroom, rounded up
    # MLX-native image generation (MFLUX / mflux-generate CLI, host MLX layer).
    # Raw measured peak working set, quantize 8 + --low-ram; admit() adds
    # MEMORY_HEADROOM_GB on top. Measured live in TASK_IMAGE_VIDEO_OVERHAUL_V1 I1.
    "mflux:schnell": 15.0,  # measured 14.49 peak MLX, q8 + --low-ram, 1024px
    "mflux:dev": 16.0,  # same FLUX.1 base as schnell, more steps
    "mflux:klein": 18.0,  # measured 17.95 peak MLX, flux2-klein-4b q8 + --low-ram
    "mflux:z-image": 30.0,  # measured 26.83GB peak MLX, z-image-turbo q8 + --low-ram, 8 steps 768px
    "mflux:qwen-image": 40.0,  # measured 36.82GB peak MLX, q8 + --low-ram, 8 steps 768px
    "mflux:qwen-image-edit": 42.0,  # same text encoder + edit transformer
    # MLX-native video generation (ltx-2-mlx CLI, host MLX layer). LTX-2.5
    # distilled, --low-ram block streaming. Measured live on the minimal
    # system in the 2026-10-28 LTX-2.3 vs 2.5 A/B (2.5 won; 2.3 removed).
    # The pack's memory scales with resolution, so the admission key is
    # size-aware: `-512` is the measured anchor, `-704` the estimated 704x480
    # job (2x the pixel area), the unsuffixed key stays for direct callers.
    "video_mlx:ltx-2.5-q4": 18.0,  # measured 15.8GiB peak footprint, --distilled --low-ram, 512x320 97fr (2026-10-28)
    "video_mlx:ltx-2.5-q4-512": 18.0,  # same measurement, the 512x320 (or smaller) admission bucket
    "video_mlx:ltx-2.5-q4-704": 25.0,  # estimated, 704x480 97fr (unmeasured — scaled from the measured 512x320 peak)
    # Fallback engine (Blaizzy/mlx-video, Wan2.2-TI2V-5B Q8): sourced 18-23GB
    # weights, estimated ~23GB peak + activations on this host (unmeasured).
    "video_mlx:wan2.2-5b": 23.0,
}

MEMORY_HEADROOM_GB: float = float(os.environ.get("MEDIA_MEMORY_HEADROOM_GB", "4.0"))
MEMORY_UNKNOWN_DEFAULT_GB: float = float(os.environ.get("MEDIA_MEMORY_UNKNOWN_DEFAULT_GB", "16.0"))
RECLAIM_TIMEOUT_S: float = float(os.environ.get("MEDIA_RECLAIM_TIMEOUT_S", "30.0"))
RECLAIM_SETTLE_TIMEOUT_S: float = float(os.environ.get("MEDIA_RECLAIM_SETTLE_TIMEOUT_S", "5.0"))
RECLAIM_POLL_INTERVAL_S: float = float(os.environ.get("MEDIA_RECLAIM_POLL_INTERVAL_S", "0.25"))


def _pipeline_url() -> str:
    """Resolve Pipeline base URL for host-native or containerized media services."""
    explicit = os.environ.get("MEDIA_PIPELINE_URL") or os.environ.get("PORTAL_PIPELINE_URL")
    if explicit:
        return explicit.strip().rstrip("/")
    env_url = os.environ.get("PIPELINE_URL", "").strip().rstrip("/")
    if env_url and (
        not env_url.startswith("http://portal-pipeline") or Path("/.dockerenv").exists()
    ):
        return env_url
    return "http://127.0.0.1:9099"


def _pipeline_api_key() -> str:
    return (os.environ.get("PIPELINE_API_KEY") or os.environ.get("PORTAL_API_KEY") or "").strip()


async def request_pipeline_reclaim(need_gib: float) -> list[dict[str, Any]] | None:
    """Ask Pipeline's load guard to evict idle LLM residents covering ``need_gib``."""
    if need_gib <= 0:
        return []
    api_key = _pipeline_api_key()
    if not api_key:
        logger.debug("Skipping pipeline reclaim: PIPELINE_API_KEY not set")
        return None
    url = f"{_pipeline_url()}/admin/reclaim-idle"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"need_gib": round(float(need_gib), 3)}
    try:
        async with httpx.AsyncClient(timeout=RECLAIM_TIMEOUT_S) as client:
            resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            logger.warning(
                "Pipeline reclaim %s returned HTTP %s: %s", url, resp.status_code, resp.text[:200]
            )
            return None
        data = resp.json()
        unloads = data.get("unloads", []) if isinstance(data, dict) else []
        return unloads if isinstance(unloads, list) else []
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Pipeline reclaim %s failed: %s", url, exc)
        return None


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
    """macOS host-native processes: reclaimable memory from vm_stat, in GB.

    "Pages free" alone undercounts real headroom by several GB on a
    long-uptime macOS host — the kernel keeps reclaimable pages in "inactive"
    (recently-evicted anonymous/file pages), "speculative" (read-ahead file
    cache), and "purgeable" (app-volunteered caches) rather than immediately
    freeing them, since it costs nothing to hold them until real pressure hits,
    at which point they're reclaimed just as fast as free pages. All three are
    counted here alongside free. Live comparison against `memory_pressure`'s "free percentage" and a
    psutil `virtual_memory().available` reading confirmed this sum tracks true available memory within ~1-2GB,
    where free+inactive alone undercounted by ~12GB with the Docker Desktop VM
    running — enough to cause a false admission refusal for a job that would
    have fit.
    """
    import subprocess

    try:
        out = subprocess.check_output(["vm_stat"], timeout=5).decode()
        page_size = 16384  # Apple Silicon default; vm_stat's header confirms this per-host
        pages: dict[str, int] = {}
        wanted = ("Pages free:", "Pages inactive:", "Pages speculative:", "Pages purgeable:")
        for line in out.splitlines():
            for label in wanted:
                if line.startswith(label):
                    pages[label] = int(line.split(":")[1].strip().rstrip("."))
        if "Pages free:" not in pages or "Pages inactive:" not in pages:
            return None
        # speculative/purgeable may be absent on older vm_stat — default to 0
        reclaimable = sum(pages.get(label, 0) for label in wanted)
        return reclaimable * page_size / 1024 / 1024 / 1024
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    return None


async def free_unified_gb() -> float | None:
    """Best-effort free host memory in GB. Returns None if no signal is available
    (callers should fail open — never block a job on an unmeasurable quantity)."""
    gb = _free_gb_from_proc_meminfo()
    if gb is not None:
        return gb
    return _free_gb_from_vm_stat()


def estimate_job_gb(model_key: str) -> tuple[float, bool]:
    """(estimated_gb, is_known). Unknown models get MEMORY_UNKNOWN_DEFAULT_GB."""
    if model_key in MEDIA_MODEL_MEMORY_GB:
        return MEDIA_MODEL_MEMORY_GB[model_key], True
    return MEMORY_UNKNOWN_DEFAULT_GB, False


async def admit(model_key: str) -> dict[str, Any] | None:
    """Returns None if the job is admitted, or a structured error dict if refused.

    Fails open (returns None / admits) when free memory can't be measured — an
    unmeasurable quantity must never block a job outright.
    """
    if MEMORY_HEADROOM_GB <= 0:
        return None  # operator-disabled (fail-open escape hatch)

    free_gb = await free_unified_gb()
    if free_gb is None:
        return None  # no signal — fail open rather than block on an unmeasurable quantity

    estimated_gb, is_known = estimate_job_gb(model_key)
    needed_gb = estimated_gb + MEMORY_HEADROOM_GB
    if needed_gb <= free_gb:
        return None

    unloads = await request_pipeline_reclaim(needed_gb - free_gb)
    if unloads is not None:
        free_gb = await free_unified_gb()
        if free_gb is None or needed_gb <= free_gb:
            return None
        if unloads and RECLAIM_SETTLE_TIMEOUT_S > 0:
            deadline = time.monotonic() + RECLAIM_SETTLE_TIMEOUT_S
            while time.monotonic() < deadline:
                await asyncio.sleep(
                    min(RECLAIM_POLL_INTERVAL_S, max(0.0, deadline - time.monotonic()))
                )
                free_gb = await free_unified_gb()
                if free_gb is None or needed_gb <= free_gb:
                    return None

    known_note = "" if is_known else " (unknown model — using a conservative default estimate)"
    return {
        "success": False,
        "retryable": True,
        "error": (
            f"Not enough free memory right now: this job needs about "
            f"{estimated_gb:.0f}GB{known_note} plus {MEMORY_HEADROOM_GB:.0f}GB headroom, "
            f"but only {free_gb:.1f}GB is free. This is temporary — free up memory and "
            "try again. Close other running models or large chats, or wait a few minutes "
            "for background models to unload."
        ),
        "operator_hint": (
            "Unload a loaded Ollama model (curl localhost:11434/api/ps to check, "
            "ollama stop <model>), or wait for the MLX generation servers (mflux :8933, "
            "video-mlx :8935) to release memory between jobs. See "
            "unit-HOWTO-media-memory-and-launch-order for the safe co-residency matrix."
        ),
    }
