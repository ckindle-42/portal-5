#!/usr/bin/env python3
"""
Portal 5 — ComfyUI Model Downloader

Downloads image/video generation models on first run.
Run by the comfyui-model-init Docker service.

Environment variables:
  IMAGE_MODEL    Image model to download: flux-schnell (default) | flux-dev | flux-uncensored | sdxl | juggernaut-xl | pony-diffusion | epicrealism-xl
  VIDEO_MODEL    Video model to download: wan2.2 (default) | wan2.2-uncensored | skyreels-v1 | mochi-1 | stable-video-diffusion
  HF_TOKEN       HuggingFace token (required for flux-dev, optional otherwise)
  MODELS_DIR     Download destination (default: /models/checkpoints)
"""
import os
import sys
from pathlib import Path

# Model specifications - module-level constant
MODELS = {
    "flux-schnell": {
        "repo_id": "black-forest-labs/FLUX.1-schnell",
        "filename": "flux1-schnell.safetensors",
        "requires_token": False,
        "size_note": "~12GB",
    },
    "flux-dev": {
        "repo_id": "black-forest-labs/FLUX.1-dev",
        "filename": "flux1-dev.safetensors",
        "requires_token": True,
        "size_note": "~24GB",
    },
    "flux-uncensored": {
        "repo_id": "enhanceaiteam/Flux-Uncensored-V2",
        "filename": None,           # full repo — multiple model files
        "requires_token": False,
        "size_note": "~24GB — explicit content, no filters",
    },
    "sdxl": {
        "repo_id": "stabilityai/stable-diffusion-xl-base-1.0",
        "filename": "sd_xl_base_1.0.safetensors",
        "requires_token": False,
        "size_note": "~7GB",
    },
    "juggernaut-xl": {
        "repo_id": "RunDiffusion/Juggernaut-XL-v9",
        "filename": "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors",
        "requires_token": False,
        "size_note": "~7GB — photoreal NSFW checkpoint",
    },
    "pony-diffusion": {
        "repo_id": "Aidynbek/PonyDiffusion-V6",
        "filename": None,           # full repo
        "requires_token": False,
        "size_note": "~8-15GB — anime/hentai style uncensored",
    },
    "epicrealism-xl": {
        "repo_id": "mattthew/epiCRealism-XL",
        "filename": None,           # full repo
        "requires_token": False,
        "size_note": "~12GB — hyperdetailed realistic",
    },
    "wan2.2": {
        "repo_id": "Wan-AI/Wan2.2-T2V-5B",
        "filename": None,   # downloads full repo
        "requires_token": False,
        "size_note": "~18GB",
    },
    "wan2.2-uncensored": {
        "repo_id": "camenduru/Wan-2.2",
        "filename": None,           # full repo — uncensored fork
        "requires_token": False,
        "size_note": "~14-20GB — uncensored Hollywood-quality video",
        "subdir": "video",         # goes into models/video/ not models/checkpoints/
    },
    "skyreels-v1": {
        "repo_id": "Skywork/SkyReels-V1",
        "filename": None,
        "requires_token": False,
        "size_note": "~15GB — cinematic human-focused video",
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


def download_model(model: str, hf_token: str, models_dir: Path) -> None:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("ERROR: huggingface_hub not installed. Run: pip install huggingface_hub")
        sys.exit(1)

    spec = MODELS[model]
    subdir = spec.get("subdir")
    if subdir:
        models_dir = models_dir.parent / subdir
    models_dir.mkdir(parents=True, exist_ok=True)

    if model not in MODELS:
        print(f"ERROR: Unknown model '{model}'. Valid: {list(MODELS.keys())}")
        sys.exit(1)

    dest = models_dir / (spec["filename"] or "")

    # Skip if already downloaded
    if spec["filename"] and dest.exists():
        size_mb = dest.stat().st_size / 1_000_000
        print(f"Skipping {model} — already downloaded ({size_mb:.0f}MB at {dest})")
        return
    elif spec["filename"] is None:
        # For full repo downloads, check if any model files exist in the target dir
        if any(models_dir.glob("*.safetensors")) or any(models_dir.glob("*.bin")):
            print(f"Skipping {model} — model files already present in {models_dir}")
            return

    # Check token requirement
    if spec["requires_token"] and not hf_token:
        print(f"WARNING: {model} requires HF_TOKEN but none provided.")
        print("Falling back to flux-schnell (no token required)")
        download_model("flux-schnell", hf_token, models_dir)
        return

    print(f"Downloading {model} ({spec['size_note']}) to {models_dir}...")
    print("This may take several minutes on first run.")

    try:
        if spec["filename"] is None:
            # Full repo download (e.g., wan2.2 which has multiple model files)
            from huggingface_hub import snapshot_download
            snapshot_download(
                repo_id=spec["repo_id"],
                local_dir=str(models_dir),
                token=hf_token if hf_token else None,
                ignore_patterns=["*.md", "*.txt"],  # skip docs, just model weights
            )
        else:
            # Single file download
            hf_hub_download(
                repo_id=spec["repo_id"],
                filename=spec["filename"],
                local_dir=str(models_dir),
                token=hf_token if hf_token else None,
            )
        print(f"Downloaded {model} successfully")
    except Exception as e:
        print(f"WARNING: Download failed: {e}")
        print("ComfyUI will start but this model won't work until downloaded manually.")
        print(f"Manual: huggingface-cli download {spec['repo_id']}")


def main() -> None:
    image_model = os.environ.get("IMAGE_MODEL", "flux-schnell")
    video_model = os.environ.get("VIDEO_MODEL", "wan2.2")
    hf_token = os.environ.get("HF_TOKEN", "")
    models_dir = Path(os.environ.get("MODELS_DIR", "/models/checkpoints"))

    print("=== Portal 5: ComfyUI Model Download ===")
    print(f"Image model: {image_model}")
    print(f"Video model: {video_model}")
    print(f"Destination: {models_dir}")
    print(f"HF_TOKEN: {'set' if hf_token else 'not set'}")
    print()

    try:
        print(f"--- Downloading image model: {image_model} ---")
        download_model(image_model, hf_token, models_dir)

        print(f"\n--- Downloading video model: {video_model} ---")
        download_model(video_model, hf_token, models_dir)

        print("\nDone. ComfyUI is ready for image and video generation.")
    except KeyboardInterrupt:
        print("\nDownload interrupted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
