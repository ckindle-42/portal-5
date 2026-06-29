"""Section C4 — Image generation: FLUX schnell."""

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
    """Image generation: FLUX schnell."""
    print("\n━━━ C4. IMAGE GENERATION — FLUX SCHNELL ━━━")
    sec = "C4"

    # Check availability
    t0 = time.time()
    code, data = await _comfyui_get("/object_info", timeout=15)
    has_flux = False
    if code == 200 and isinstance(data, dict):
        ckpt_node = data.get("CheckpointLoaderSimple", {})
        ckpts = ckpt_node.get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
        flux_ckpts = [c for c in ckpts if "flux" in c.lower() and "schnell" in c.lower()]
        has_flux = bool(flux_ckpts)
        record(
            sec,
            "C4-01",
            "FLUX schnell checkpoint installed",
            "PASS" if has_flux else "INFO",
            f"{flux_ckpts[0]}"
            if flux_ckpts
            else "not installed — download: huggingface-cli download black-forest-labs/FLUX.1-schnell",
            t0=t0,
        )
    else:
        record(
            sec,
            "C4-01",
            "FLUX schnell checkpoint installed",
            "WARN",
            f"ComfyUI not reachable (HTTP {code})",
            t0=t0,
        )

    if not has_flux:
        record(
            sec,
            "C4-02",
            "FLUX schnell generation via MCP",
            "INFO",
            "skipped — checkpoint not installed",
            t0=None,
        )
        record(
            sec,
            "C4-03",
            "FLUX schnell output accessible via ComfyUI",
            "INFO",
            "skipped — checkpoint not installed",
            t0=None,
        )
        return

    # Generate via MCP
    await _wait_for_comfyui_idle()
    await _mcp(
        COMFYUI_MCP_PORT,
        "generate_image",
        {
            "prompt": "a red apple on a wooden table, photorealistic, studio lighting",
            "steps": 4,
            "seed": 42,
            "checkpoint": flux_ckpts[0],
        },
        section=sec,
        tid="C4-02",
        name="FLUX schnell: generate_image (4 steps)",
        ok_fn=lambda t: (
            "success" in t.lower()
            or "url" in t.lower()
            or "filename" in t.lower()
            or "output" in t.lower()
        ),
        detail_fn=lambda t: t[:200],
        warn_if=["error", "failed", "rejected", "not available"],
    )

    # Verify output accessible from ComfyUI /view endpoint
    t0 = time.time()
    code, data = await _comfyui_get("/history?max_items=1")
    if code == 200 and isinstance(data, dict) and data:
        # Find the most recent image output
        latest_key = next(iter(data))
        outputs = data[latest_key].get("outputs", {})
        found_image = False
        for node_outputs in outputs.values():
            images = node_outputs.get("images", [])
            if images:
                img = images[0]
                fname = img.get("filename", "")
                subfolder = img.get("subfolder", "")
                ftype = img.get("type", "output")
                # Try to fetch the image
                params = f"filename={fname}&subfolder={subfolder}&type={ftype}"
                img_code, _ = await _comfyui_get(f"/view?{params}", timeout=10)
                found_image = img_code == 200
                record(
                    sec,
                    "C4-03",
                    "FLUX schnell output accessible via /view",
                    "PASS" if found_image else "WARN",
                    f"{fname} — HTTP {img_code}" if fname else "no filename in history",
                    t0=t0,
                )
                break
        if not found_image:
            record(
                sec,
                "C4-03",
                "FLUX schnell output accessible via /view",
                "WARN",
                "no image outputs found in ComfyUI history",
                t0=t0,
            )
    else:
        record(
            sec,
            "C4-03",
            "FLUX schnell output accessible via /view",
            "WARN",
            f"ComfyUI /history returned HTTP {code}",
            t0=t0,
        )
