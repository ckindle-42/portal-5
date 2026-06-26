"""Section C5 — Image generation: FLUX dev."""
from __future__ import annotations

import time

from ._common import (
    COMFYUI_MCP_PORT,
    _comfyui_get,
    _mcp,
    _wait_for_comfyui_idle,
    record,
)


async def run() -> None:
    """Image generation: FLUX dev."""
    print("\n━━━ C5. IMAGE GENERATION — FLUX DEV (optional) ━━━")
    sec = "C5"

    t0 = time.time()
    code, data = await _comfyui_get("/object_info", timeout=15)
    has_flux_dev = False
    flux_dev_ckpt = ""
    if code == 200 and isinstance(data, dict):
        ckpt_node = data.get("CheckpointLoaderSimple", {})
        ckpts = ckpt_node.get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
        flux_dev_ckpts = [c for c in ckpts if "flux" in c.lower() and "dev" in c.lower()]
        has_flux_dev = bool(flux_dev_ckpts)
        flux_dev_ckpt = flux_dev_ckpts[0] if flux_dev_ckpts else ""
        record(
            sec,
            "C5-01",
            "FLUX dev checkpoint installed",
            "PASS" if has_flux_dev else "INFO",
            flux_dev_ckpt
            if has_flux_dev
            else "not installed (optional) — download: huggingface-cli download black-forest-labs/FLUX.1-dev",
            t0=t0,
        )
    else:
        record(
            sec,
            "C5-01",
            "FLUX dev checkpoint installed",
            "WARN",
            f"ComfyUI not reachable (HTTP {code})",
            t0=t0,
        )
        return

    if not has_flux_dev:
        record(
            sec,
            "C5-02",
            "FLUX dev generation via MCP",
            "INFO",
            "skipped — checkpoint not installed",
            t0=None,
        )
        return

    await _wait_for_comfyui_idle()
    await _mcp(
        COMFYUI_MCP_PORT,
        "generate_image",
        {
            "prompt": "mountain landscape at sunrise, dramatic golden hour lighting, 8k detail, photorealistic, professional photography",
            "steps": 28,
            "cfg": 3.5,
            "seed": 42,
            "checkpoint": flux_dev_ckpt,
        },
        section=sec,
        tid="C5-02",
        name="FLUX dev: generate_image (28 steps, cfg=3.5)",
        ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
        detail_fn=lambda t: t[:200],
        warn_if=["error", "failed", "rejected"],
    )

    # LoRA tests — verify both regular and NSFW LoRAs work with image generation
    code, lora_data = await _comfyui_get("/object_info/LoraLoader", timeout=15)
    loras: list[str] = []
    if code == 200 and isinstance(lora_data, dict):
        lora_node = lora_data.get("LoraLoader", {})
        entries = lora_node.get("input", {}).get("required", {}).get("lora_name", [])
        if entries and isinstance(entries[0], list):
            loras = entries[0]

    # Regular LoRA test
    regular_loras = [l for l in loras if "nsfw" not in l.lower()]
    if regular_loras:
        await _wait_for_comfyui_idle()
        await _mcp(
            COMFYUI_MCP_PORT,
            "generate_image",
            {
                "prompt": "portrait of a woman, highly detailed face, soft studio lighting, photorealistic, 8k",
                "steps": 28,
                "cfg": 3.5,
                "seed": 42,
                "checkpoint": flux_dev_ckpt,
                "lora": regular_loras[0],
                "lora_strength": 0.8,
            },
            section=sec,
            tid="C5-03",
            name=f"LoRA generation: {regular_loras[0]} (FLUX dev, 28 steps)",
            ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
            detail_fn=lambda t: t[:200],
            warn_if=["error", "failed", "rejected"],
        )
    else:
        record(
            sec, "C5-03", "LoRA generation (regular)", "WARN", "no regular LoRA installed", t0=None
        )

    # NSFW image test — use the uncensored Flux_v8-NSFW checkpoint (not the video LoRA)
    code_ckpt, data_ckpt = await _comfyui_get("/object_info/CheckpointLoaderSimple", timeout=15)
    all_ckpts: list[str] = []
    if code_ckpt == 200 and isinstance(data_ckpt, dict):
        entries = (
            data_ckpt.get("CheckpointLoaderSimple", {})
            .get("input", {})
            .get("required", {})
            .get("ckpt_name", [])
        )
        if entries and isinstance(entries[0], list):
            all_ckpts = entries[0]
    nsfw_image_ckpts = [c for c in all_ckpts if "nsfw" in c.lower()]

    if nsfw_image_ckpts:
        await _wait_for_comfyui_idle()
        await _mcp(
            COMFYUI_MCP_PORT,
            "generate_image",
            {
                "prompt": "nsfwsks, artistic nude portrait, dramatic studio lighting, highly detailed, photorealistic, 8k",
                "steps": 28,
                "cfg": 3.5,
                "seed": 42,
                "checkpoint": nsfw_image_ckpts[0],
            },
            section=sec,
            tid="C5-04",
            name=f"NSFW checkpoint: {nsfw_image_ckpts[0]} (28 steps)",
            ok_fn=lambda t: "success" in t.lower() or "url" in t.lower() or "filename" in t.lower(),
            detail_fn=lambda t: t[:200],
            warn_if=["error", "failed", "rejected"],
        )
    else:
        record(
            sec,
            "C5-04",
            "NSFW checkpoint generation",
            "WARN",
            "no NSFW checkpoint installed (e.g. Flux_v8-NSFW.safetensors)",
            t0=None,
        )

