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
tier). These estimates are measured peak working sets and mirrored from
`unit-fact-media-memory-budget` (portal/platform/wiki/adapters/seed_facts.py) — kept
as a separate copy here rather than imported, matching Rule 3 (MCP modules are
independent services, zero cross-imports from platform internals).
"""

from __future__ import annotations

import os

MEDIA_MODEL_MEMORY_GB: dict[str, float] = {
    "comfyui:flux-schnell": 27.2,  # checkpoint 22 + vae 0.32 + clip_l 0.235 + t5xxl_fp8 4.6
    "comfyui:sdxl": 6.5,  # single self-contained checkpoint
    # Static weights total about 38.2GB, but diffusion activation and buffer
    # overhead push the measured peak close to the full 64GB unified pool even
    # for a tiny 9-frame, 5-step job.
    "video:wan21-nsfw": 55.0,
    # Measured live (Phase 5): MiniMax-Music3-MLX 60s/30-step, vm_stat delta + headroom.
    "music:minimax3": 27.0,  # coarse sampled delta 22.02GiB + 4GiB headroom, rounded up
    # Measured live (Phase 5): ACE-Step-1.5 sft 2B + 1.7B LM 60s/30-step, vm_stat delta + headroom.
    "music:acestep-sft": 40.0,  # coarse sampled delta 35.43GiB + 4GiB headroom, rounded up
    # Rationale, incident history: unit-known-limitations-qwen-image-bf16-crashes-on-apple-silicon-mps
    "comfyui:qwen-image-2512": 38.0,  # fp8 diffusion 20.4 + fp8_scaled text encoder 9.4 + vae 0.25 static + margin
    "comfyui:qwen-image-2512-lightning": 39.0,  # same base weights (QWEN_IMAGE_MODEL, fp8) + ~0.85GB LoRA
    "comfyui:qwen-image-edit-2509": 38.0,  # plain fp8 storage expands to bf16 compute; live 512px peak used ~34GB
    "comfyui:qwen-image-edit-2511": 60.0,  # bf16 diffusion 40.8 (no smaller variant yet) + fp8_scaled text encoder 9.4 + vae 0.25 static + margin
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
    """macOS host-native processes: reclaimable memory from vm_stat, in GB.

    "Pages free" alone undercounts real headroom by several GB on a
    long-uptime macOS host — the kernel keeps reclaimable pages in "inactive"
    (recently-evicted anonymous/file pages), "speculative" (read-ahead file
    cache), and "purgeable" (app-volunteered caches) rather than immediately
    freeing them, since it costs nothing to hold them until real pressure hits,
    at which point they're reclaimed just as fast as free pages. All three are
    counted here alongside free. Live comparison against ComfyUI's own
    psutil-based system_stats (`ram_free`) and `memory_pressure`'s "free
    percentage" confirmed this sum tracks true available memory within ~1-2GB,
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
            "ollama stop <model>), or stop ComfyUI "
            "(launchctl kickstart -k gui/$(id -u)/com.portal5.comfyui) after unloading "
            "any large model. See unit-HOWTO-media-memory-and-launch-order for the safe "
            "co-residency matrix."
        ),
    }
