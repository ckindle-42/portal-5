"""Section C1 — ComfyUI direct API (system stats, object info, models)."""
from __future__ import annotations

import time

from ._common import (
    _comfyui_get,
    record,
)


async def run() -> None:
    """ComfyUI direct API (system stats, object info, models)."""
    print("\n━━━ C1. COMFYUI DIRECT API ━━━")
    sec = "C1"

    # System stats
    t0 = time.time()
    code, data = await _comfyui_get("/system_stats")
    if code == 200 and isinstance(data, dict):
        system = data.get("system", {})
        detail = (
            f"Python {system.get('python_version', '?')}, "
            f"ComfyUI version {data.get('comfyui_version', '?')}"
        )
        record(sec, "C1-01", "ComfyUI system_stats", "PASS", detail, t0=t0)
    else:
        record(
            sec,
            "C1-01",
            "ComfyUI system_stats",
            "WARN",
            f"HTTP {code}" if code != 0 else str(data)[:80],
            t0=t0,
        )

    # Prompt queue state
    t0 = time.time()
    code, data = await _comfyui_get("/queue")
    if code == 200 and isinstance(data, dict):
        running = len(data.get("queue_running", []))
        pending = len(data.get("queue_pending", []))
        record(
            sec,
            "C1-02",
            "ComfyUI /queue reachable",
            "PASS",
            f"running={running} pending={pending}",
            t0=t0,
        )
    else:
        record(
            sec,
            "C1-02",
            "ComfyUI /queue reachable",
            "WARN",
            f"HTTP {code}: {str(data)[:80]}",
            t0=t0,
        )

    # Object info (node catalogue)
    t0 = time.time()
    code, data = await _comfyui_get("/object_info", timeout=15)
    if code == 200 and isinstance(data, dict):
        node_count = len(data)
        # Check for key nodes we depend on
        required_nodes = ["KSampler", "CLIPTextEncode", "VAEDecode", "SaveImage"]
        missing_nodes = [n for n in required_nodes if n not in data]
        record(
            sec,
            "C1-03",
            "ComfyUI /object_info (node catalogue)",
            "PASS" if not missing_nodes else "WARN",
            f"{node_count} nodes registered"
            + (f" — missing: {missing_nodes}" if missing_nodes else ""),
            t0=t0,
        )
    else:
        record(
            sec,
            "C1-03",
            "ComfyUI /object_info (node catalogue)",
            "WARN",
            f"HTTP {code}: {str(data)[:80]}",
            t0=t0,
        )

    # Checkpoint model discovery via /object_info
    t0 = time.time()
    checkpoints: list[str] = []
    if code == 200 and isinstance(data, dict):
        ckpt_node = data.get("CheckpointLoaderSimple", {})
        input_types = ckpt_node.get("input", {}).get("required", {})
        ckpt_entry = input_types.get("ckpt_name", [])
        if ckpt_entry and isinstance(ckpt_entry[0], list):
            checkpoints = ckpt_entry[0]
    record(
        sec,
        "C1-04",
        "Checkpoint models installed",
        "PASS" if checkpoints else "WARN",
        f"{len(checkpoints)} checkpoint(s): {', '.join(checkpoints[:5])}"
        if checkpoints
        else "none found — check ComfyUI models/checkpoints/",
        t0=t0,
    )

    # VAE discovery
    t0 = time.time()
    vaes: list[str] = []
    if code == 200 and isinstance(data, dict):
        vae_node = data.get("VAELoader", {})
        input_types = vae_node.get("input", {}).get("required", {})
        vae_entry = input_types.get("vae_name", [])
        if vae_entry and isinstance(vae_entry[0], list):
            vaes = vae_entry[0]
    record(
        sec,
        "C1-05",
        "VAE models installed",
        "PASS" if vaes else "INFO",
        f"{len(vaes)} VAE(s): {', '.join(vaes[:5])}"
        if vaes
        else "none (using checkpoint-embedded VAE)",
        t0=t0,
    )

    # LoRA discovery
    t0 = time.time()
    loras: list[str] = []
    if code == 200 and isinstance(data, dict):
        lora_node = data.get("LoraLoader", {})
        input_types = lora_node.get("input", {}).get("required", {})
        lora_entry = input_types.get("lora_name", [])
        if lora_entry and isinstance(lora_entry[0], list):
            loras = lora_entry[0]
    record(
        sec,
        "C1-06",
        "LoRA models installed",
        "PASS" if loras else "WARN",
        f"{len(loras)} LoRA(s): {', '.join(loras[:5])}"
        if loras
        else "none installed — download at least one LoRA",
        t0=t0,
    )

    # Upscale models
    t0 = time.time()
    upscalers: list[str] = []
    if code == 200 and isinstance(data, dict):
        up_node = data.get("UpscaleModelLoader", {})
        input_types = up_node.get("input", {}).get("required", {})
        up_entry = input_types.get("model_name", [])
        # ComfyUI returns ['COMBO', {'options': ['model1', 'model2']}] for upscale
        if up_entry and isinstance(up_entry, list) and len(up_entry) > 1:
            if isinstance(up_entry[1], dict):
                upscalers = up_entry[1].get("options", [])
            elif isinstance(up_entry[0], list):
                upscalers = up_entry[0]
    record(
        sec,
        "C1-07",
        "Upscale models installed",
        "PASS" if upscalers else "WARN",
        f"{len(upscalers)} upscaler(s): {', '.join(upscalers[:5])}"
        if upscalers
        else "none installed — download an upscale model (e.g. RealESRGAN_x4.pth)",
        t0=t0,
    )

    # Store checkpoints for later sections
    return checkpoints

