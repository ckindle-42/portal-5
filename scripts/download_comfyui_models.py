#!/usr/bin/env python3
"""
Portal 5 — ComfyUI Model Downloader

Downloads image and video generation models on first run.
Run by the comfyui-model-init Docker service.

Environment variables:
  IMAGE_MODEL    Image model key (default: flux-schnell)
  VIDEO_MODEL    Video model key (default: wan2.2)
  HF_TOKEN       HuggingFace token (required for flux-dev, optional otherwise)
  MODELS_DIR     Download destination (default: /models/checkpoints)
"""

import os
import sys
from pathlib import Path

# ── Image model specifications ───────────────────────────────────────────────
IMAGE_MODELS: dict = {
    "flux-schnell": {
        "repo_id": "black-forest-labs/FLUX.1-schnell",
        "filename": "flux1-schnell.safetensors",
        "requires_token": False,
        "size_note": "~12GB — fast, clean, default",
    },
    "flux-dev": {
        "repo_id": "black-forest-labs/FLUX.1-dev",
        "filename": "flux1-dev.safetensors",
        "requires_token": True,
        "size_note": "~24GB — high quality, requires HF_TOKEN",
    },
    "flux-uncensored": {
        "repo_id": "enhanceaiteam/Flux-Uncensored-V2",
        "filename": None,
        "requires_token": False,
        "size_note": "~24GB — hyper-realistic NSFW, zero filters",
    },
    "flux2-klein": {
        "repo_id": "black-forest-labs/FLUX.2-schnell",
        "filename": None,
        "requires_token": False,
        "size_note": "~20GB — next-gen Flux, superior composition/lighting",
        "note": "Use uncensored LoRAs from HF for NSFW. If FLUX.2-schnell unavailable, "
        "try: black-forest-labs/FLUX.2-dev (requires token)",
    },
    "sdxl": {
        "repo_id": "stabilityai/stable-diffusion-xl-base-1.0",
        "filename": "sd_xl_base_1.0.safetensors",
        "requires_token": False,
        "size_note": "~7GB — versatile baseline",
    },
    "juggernaut-xl": {
        "repo_id": "RunDiffusion/Juggernaut-XL-v9",
        "filename": "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors",
        "requires_token": False,
        "size_note": "~7GB — photoreal NSFW checkpoint, anatomy-accurate",
        "fallback_note": "If not on HF, download safetensors from CivitAI manually to MODELS_DIR",
    },
    "pony-diffusion": {
        "repo_id": "Aidynbek/PonyDiffusion-V6",
        "filename": None,
        "requires_token": False,
        "size_note": "~12GB — anime/hentai uncensored style",
    },
    "epicrealism-xl": {
        "repo_id": "mattthew/epiCRealism-XL",
        "filename": None,
        "requires_token": False,
        "size_note": "~12GB — hyperdetailed realistic adult scenes",
    },
}

# ── Video model specifications ────────────────────────────────────────────────
VIDEO_MODELS: dict = {
    "wan2.2": {
        "repo_id": "FX-FeiHou/wan2.2-Remix",
        "filename": None,
        "requires_token": False,
        "size_note": "~18GB — Wan2.2 Remix v2.1, better consistency + M4 Pro low-VRAM",
        "subdir": "video",
        "download_note": (
            "huggingface-cli download FX-FeiHou/wan2.2-Remix --include '*.safetensors'\n"
            "After download, check ~/ComfyUI/models/video/ for the actual filename\n"
            "and set WAN22_MODEL_FILE in .env to match."
        ),
    },
    "wan2.2-uncensored": {
        "repo_id": "camenduru/Wan-2.2",
        "filename": None,
        "requires_token": False,
        "size_note": "~20GB — uncensored fork, Hollywood motion control",
        "subdir": "video",
    },
    "skyreels-v1": {
        "repo_id": "Skywork/SkyReels-V1",
        "filename": None,
        "requires_token": False,
        "size_note": "~15GB — cinematic human-focused video with sound",
        "subdir": "video",
    },
    "mochi-1": {
        "repo_id": "genmo/mochi-1-preview",
        "filename": None,
        "requires_token": False,
        "size_note": "~15GB — long-form storytelling video (Apache 2.0)",
        "subdir": "video",
    },
    "stable-video-diffusion": {
        "repo_id": "stabilityai/stable-video-diffusion-img2vid-xt",
        "filename": "svd_xt.safetensors",
        "requires_token": False,
        "size_note": "~10GB — image-to-video animation",
        "subdir": "video",
    },
}

# Combined for validation
ALL_MODELS = {**IMAGE_MODELS, **VIDEO_MODELS}


def _resolve_dir(base_dir: Path, spec: dict) -> Path:
    """Resolve download directory, handling video subdir."""
    subdir = spec.get("subdir")
    target = base_dir.parent / subdir if subdir else base_dir
    target.mkdir(parents=True, exist_ok=True)
    return target


def download_model(model: str, hf_token: str, models_dir: Path) -> None:
    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except ImportError:
        print("ERROR: huggingface_hub not installed. Run: pip install huggingface_hub")
        sys.exit(1)

    if model not in ALL_MODELS:
        print(f"ERROR: Unknown model '{model}'.")
        print(f"  Image models: {', '.join(IMAGE_MODELS.keys())}")
        print(f"  Video models: {', '.join(VIDEO_MODELS.keys())}")
        sys.exit(1)

    spec = ALL_MODELS[model]
    target_dir = _resolve_dir(models_dir, spec)

    # Skip if already downloaded
    if spec["filename"] and (target_dir / spec["filename"]).exists():
        size_mb = (target_dir / spec["filename"]).stat().st_size / 1_000_000
        print(f"Skipping {model} — already present ({size_mb:.0f}MB at {target_dir})")
        return
    elif spec["filename"] is None:
        if any(target_dir.glob("*.safetensors")) or any(target_dir.glob("*.bin")):
            print(f"Skipping {model} — model files already present in {target_dir}")
            return

    # Token check
    if spec.get("requires_token") and not hf_token:
        print(f"WARNING: {model} requires HF_TOKEN but none provided.")
        fallback = "flux-schnell"
        print(f"Falling back to {fallback}")
        download_model(fallback, hf_token, models_dir)
        return

    if "note" in spec:
        print(f"NOTE: {spec['note']}")

    print(f"Downloading {model} ({spec['size_note']}) to {target_dir}...")
    print("This may take several minutes on first run.")

    try:
        if spec["filename"] is None:
            snapshot_download(
                repo_id=spec["repo_id"],
                local_dir=str(target_dir),
                token=hf_token if hf_token else None,
                ignore_patterns=["*.md", "*.txt", ".gitattributes", "*.json"],
            )
        else:
            hf_hub_download(
                repo_id=spec["repo_id"],
                filename=spec["filename"],
                local_dir=str(target_dir),
                token=hf_token if hf_token else None,
            )
        print(f"Downloaded {model} successfully")
        if model == "wan2.2":
            print("")
            print("  ⚠️  Wan2.2 Remix filenames vary by release.")
            print(f"  Check: ls {target_dir}/*.safetensors")
            print("  Then update WAN22_MODEL_FILE in .env to match the actual filename.")
    except Exception as e:
        fallback_note = spec.get("fallback_note", "")
        print(f"WARNING: Download failed: {e}")
        if fallback_note:
            print(f"Fallback: {fallback_note}")
        else:
            print(f"Manual: huggingface-cli download {spec['repo_id']}")
        print("ComfyUI will start but this model won't be available until downloaded.")


def main() -> None:
    image_model = os.environ.get("IMAGE_MODEL", "flux-schnell")
    video_model = os.environ.get("VIDEO_MODEL", "wan2.2")
    hf_token = os.environ.get("HF_TOKEN", "")
    models_dir = Path(os.environ.get("MODELS_DIR", "/models/checkpoints"))

    print("=== Portal 5: ComfyUI Model Download ===")
    print(
        f"Image model: {image_model}  ({IMAGE_MODELS.get(image_model, {}).get('size_note', 'unknown')})"
    )
    print(
        f"Video model: {video_model}  ({VIDEO_MODELS.get(video_model, {}).get('size_note', 'unknown')})"
    )
    print(f"Destination: {models_dir}")
    print(f"HF_TOKEN:    {'set' if hf_token else 'not set'}")
    print()

    print(f"--- Image model: {image_model} ---")
    download_model(image_model, hf_token, models_dir)

    print(f"\n--- Video model: {video_model} ---")
    download_model(video_model, hf_token, models_dir)

    print("\nDone. ComfyUI is ready for image and video generation.")


if __name__ == "__main__":
    main()
