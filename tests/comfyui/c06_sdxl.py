"""Section C6 — Image generation: SDXL variants."""

from __future__ import annotations

import time

from ._common import (
    COMFYUI_MCP_PORT,
    _comfyui_get,
    _filter_checkpoints,
    _mcp,
    _wait_for_comfyui_idle,
    record,
)


async def run() -> None:
    """Image generation: SDXL variants."""
    """Test every installed SDXL / XL-family checkpoint.

    Discovers all XL-family checkpoints dynamically (sd_xl_base, Juggernaut-XL,
    RealVisXL, Animagine-XL, SDXL-Turbo, pony-diffusion, epicrealism, etc.) and
    generates one image per checkpoint using the SDXL workflow.  NSFW-capable
    checkpoints get prompts that exercise that capability.
    """
    print("\n━━━ C6. IMAGE GENERATION — SDXL & XL VARIANTS ━━━")
    sec = "C6"

    t0 = time.time()
    code, data = await _comfyui_get("/object_info", timeout=15)
    if code != 200 or not isinstance(data, dict):
        record(
            sec,
            "C6-00",
            "XL checkpoint discovery",
            "WARN",
            f"ComfyUI not reachable (HTTP {code})",
            t0=t0,
        )
        return

    raw_ckpts = (
        data.get("CheckpointLoaderSimple", {})
        .get("input", {})
        .get("required", {})
        .get("ckpt_name", [[]])[0]
    )
    all_ckpts = _filter_checkpoints(raw_ckpts)

    # XL/SDXL family — any non-Flux checkpoint whose name contains XL-family keywords.
    # Keeps sd_xl_base, juggernaut-xl, realvis, animagine, sdxl-turbo, pony, epicrealism, etc.
    xl_patterns = ["xl", "sdxl", "juggernaut", "pony", "epic", "realistic", "animagine", "turbo"]
    xl_ckpts = [
        c for c in all_ckpts if any(p in c.lower() for p in xl_patterns) and "flux" not in c.lower()
    ]

    t0 = time.time()
    if not xl_ckpts:
        record(
            sec,
            "C6-00",
            "XL/SDXL checkpoints installed",
            "INFO",
            "none found — download juggernaut-xl, realvis-xl, animagine-xl-3.1, or sdxl-turbo",
            t0=t0,
        )
        return

    record(
        sec,
        "C6-00",
        "XL/SDXL checkpoints discovered",
        "INFO",
        f"{len(xl_ckpts)} found: {', '.join(xl_ckpts)}",
        t0=t0,
    )

    # Per-checkpoint prompt selection — NSFW-capable models get prompts that exercise
    # their uncensored range; style-specific models get matching prompts.
    nsfw_prompts: dict[str, str] = {
        "juggernaut": "RAW photo, nsfw, nude woman, dramatic studio lighting, photorealistic, hyperdetailed skin, 8k UHD",
        "realvis": "nsfw, nude, photorealistic woman, soft bedroom lighting, highly detailed, 8k UHD, sharp focus",
        "epic": "nsfw, nude, photorealistic, dramatic rim lighting, hyperdetailed, cinematic",
        "pony": "score_9, score_8_up, nsfw, explicit, anime girl, extremely detailed face, 8k",
        "animagine": "1girl, masterpiece, best quality, anime style, extremely detailed face and eyes, soft lighting",
        "turbo": "futuristic city at night, neon lights, cyberpunk style, ultra-detailed, cinematic",
    }
    negative = "blurry, low quality, watermark, deformed, bad anatomy, extra limbs, mutated, ugly, poorly drawn"

    for i, ckpt in enumerate(xl_ckpts, 1):
        ck_lower = ckpt.lower()
        prompt = next(
            (v for k, v in nsfw_prompts.items() if k in ck_lower),
            "futuristic cityscape at golden hour, dramatic lighting, ultra-detailed, photorealistic, 8k UHD",
        )
        # SDXL-Turbo is distilled: cfg≈0, 4 steps max. All others: 35 steps for quality.
        is_turbo = "turbo" in ck_lower
        steps = 4 if is_turbo else 35
        cfg = 0.0 if is_turbo else 7.5
        neg = "" if is_turbo else negative

        await _wait_for_comfyui_idle()
        await _mcp(
            COMFYUI_MCP_PORT,
            "generate_image",
            {
                "prompt": prompt,
                "negative_prompt": neg,
                "steps": steps,
                "cfg": cfg,
                "seed": 42,
                "width": 1024,
                "height": 1024,
                "model": "sdxl",
                "checkpoint": ckpt,
            },
            section=sec,
            tid=f"C6-{i:02d}",
            name=f"XL variant: {ckpt[:55]}",
            ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
            detail_fn=lambda t: t[:200],
            warn_if=["error", "failed", "rejected"],
        )
