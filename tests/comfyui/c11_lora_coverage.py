"""Section C11 — All LoRAs x FLUX schnell coverage."""

from __future__ import annotations

import time

import httpx

from ._common import (
    COMFYUI_MCP_PORT,
    VIDEO_MCP_PORT,
    _comfyui_get,
    _filter_checkpoints,
    _mcp,
    _wait_for_comfyui_idle,
    record,
)


async def run() -> None:
    """All LoRAs x FLUX schnell coverage."""
    """Test every installed LoRA with the appropriate FLUX base model.

    C5 tests only the first regular LoRA and first NSFW LoRA found.  This section
    exhaustively covers all installed LoRAs so that any newly added LoRA is
    automatically picked up and validated without test changes.

    Base model selection:
    - LoRAs with "dev" in their name → FLUX dev (20 steps): dev LoRAs produce noise on schnell
    - All other LoRAs → FLUX schnell (4 steps): fast path for schnell-compatible LoRAs
    FLUX dev is used as fallback if schnell is not installed.
    """
    print("\n━━━ C11. ALL LORAS × FLUX ━━━")
    sec = "C11"

    t0 = time.time()
    code, data = await _comfyui_get("/object_info", timeout=15)
    if code != 200 or not isinstance(data, dict):
        record(
            sec, "C11-01", "LoRA inventory", "WARN", f"ComfyUI not reachable (HTTP {code})", t0=t0
        )
        return

    raw_ckpts = (
        data.get("CheckpointLoaderSimple", {})
        .get("input", {})
        .get("required", {})
        .get("ckpt_name", [[]])[0]
    )
    real_ckpts = _filter_checkpoints(raw_ckpts)
    loras: list[str] = (
        data.get("LoraLoader", {}).get("input", {}).get("required", {}).get("lora_name", [[]])[0]
        or []
    )

    # Inventory
    record(
        sec,
        "C11-01",
        "LoRA inventory",
        "PASS" if loras else "INFO",
        f"{len(loras)} LoRA(s) installed: {', '.join(loras)}" if loras else "no LoRAs installed",
        t0=t0,
    )

    if not loras:
        return

    flux_schnell = next((c for c in real_ckpts if "schnell" in c.lower()), None)
    flux_dev = next(
        (
            c
            for c in real_ckpts
            if "dev" in c.lower() and "flux" in c.lower() and "nsfw" not in c.lower()
        ),
        None,
    )

    if not flux_schnell and not flux_dev:
        record(
            sec,
            "C11-02",
            "LoRA base models",
            "WARN",
            "Neither FLUX schnell nor FLUX dev installed — cannot run LoRA suite",
            t0=None,
        )
        return

    record(
        sec,
        "C11-02",
        "LoRA base models",
        "INFO",
        f"schnell={flux_schnell or 'not found'}, dev={flux_dev or 'not found'}",
        t0=time.time(),
    )

    # Identify video-only LoRAs (HunyuanVideo, Wan2.2) — they are incompatible with
    # FLUX image generation and are already tested in C8. Query video_mcp for its
    # configured video LoRA so we can exclude it here.
    video_loras: set[str] = set()
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            await c.get(f"http://localhost:{VIDEO_MCP_PORT}/health")
            # Ask Docker container env which LoRA video_mcp uses
            pass
    except Exception:
        pass
    # nsfw-e7.safetensors is the HunyuanVideo NSFW LoRA — video-only, not FLUX-compatible.
    # Hardcode the default; also detect by checking if lora name contains "hunyuan"/"wan".
    video_loras.add("nsfw-e7.safetensors")

    # Generate one image per LoRA.  Base model chosen by LoRA type:
    # - "dev" in name → FLUX dev (28 steps): dev LoRAs include CLIP weights, need dev base
    # - otherwise → FLUX schnell (4 steps, fast)
    # Video LoRAs are skipped here — they are tested in C8 with the video_mcp.
    for i, lora in enumerate(loras, 3):
        lo = lora.lower()

        if lora in video_loras or any(k in lo for k in ["hunyuan", "wan22", "wan2"]):
            record(
                sec,
                f"C11-{i:02d}",
                f"LoRA: {lora[:55]}",
                "INFO",
                "video-only LoRA — skipped for image generation (tested in C8)",
                t0=None,
            )
            continue

        is_dev_lora = "dev" in lo
        if is_dev_lora and flux_dev:
            checkpoint = flux_dev
            steps = 28
        else:
            checkpoint = flux_schnell or flux_dev
            steps = 4

        if any(k in lo for k in ["nsfw", "explicit", "adult", "hentai", "nude", "erotic"]):
            prompt = "nsfwsks, photorealistic portrait, dramatic studio lighting, 8k detail"
        elif any(k in lo for k in ["frost", "araminta", "portrait", "style"]):
            prompt = "portrait of a woman, detailed face, soft studio lighting, photorealistic"
        else:
            prompt = "a beautiful landscape, dramatic sky, professional photography, 8k"

        await _wait_for_comfyui_idle()
        await _mcp(
            COMFYUI_MCP_PORT,
            "generate_image",
            {
                "prompt": prompt,
                "steps": steps,
                "seed": 42,
                "checkpoint": checkpoint,
                "lora": lora,
                "lora_strength": 0.8,
            },
            section=sec,
            tid=f"C11-{i:02d}",
            name=f"LoRA: {lora[:45]} ({steps}s, {checkpoint[:20] if checkpoint else '?'})",
            ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
            detail_fn=lambda t: t[:200],
            warn_if=["error", "failed"],
        )
