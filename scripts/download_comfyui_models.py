#!/usr/bin/env python3
"""
Portal 5 — ComfyUI Model Downloader

Downloads image/video generation models on first run.
Run by the comfyui-model-init Docker service.

Environment variables:
  IMAGE_MODEL    Model to download: flux-schnell (default) | flux-dev | sdxl | wan2.2
  HF_TOKEN       HuggingFace token (required for flux-dev, optional otherwise)
  MODELS_DIR     Download destination (default: /models/checkpoints)
"""
import os
import sys
from pathlib import Path


def download_model(model: str, hf_token: str, models_dir: Path) -> None:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("ERROR: huggingface_hub not installed. Run: pip install huggingface_hub")
        sys.exit(1)

    models_dir.mkdir(parents=True, exist_ok=True)

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
        "sdxl": {
            "repo_id": "stabilityai/stable-diffusion-xl-base-1.0",
            "filename": "sd_xl_base_1.0.safetensors",
            "requires_token": False,
            "size_note": "~7GB",
        },
        "wan2.2": {
            "repo_id": "Wan-AI/Wan2.2-T2V-5B",
            "filename": None,   # downloads full repo
            "requires_token": False,
            "size_note": "~18GB",
        },
    }

    if model not in MODELS:
        print(f"ERROR: Unknown model '{model}'. Valid: {list(MODELS.keys())}")
        sys.exit(1)

    spec = MODELS[model]
    dest = models_dir / (spec["filename"] or "")

    # Skip if already downloaded
    if spec["filename"] and dest.exists():
        size_mb = dest.stat().st_size / 1_000_000
        print(f"Skipping {model} — already downloaded ({size_mb:.0f}MB at {dest})")
        return

    # Check token requirement
    if spec["requires_token"] and not hf_token:
        print(f"WARNING: {model} requires HF_TOKEN but none provided.")
        print("Falling back to flux-schnell (no token required)")
        download_model("flux-schnell", hf_token, models_dir)
        return

    print(f"Downloading {model} ({spec['size_note']}) to {models_dir}...")
    print("This may take several minutes on first run.")

    kwargs = {
        "repo_id": spec["repo_id"],
        "local_dir": str(models_dir),
    }
    if spec["filename"]:
        kwargs["filename"] = spec["filename"]
    if hf_token:
        kwargs["token"] = hf_token

    try:
        hf_hub_download(**kwargs)
        print(f"Downloaded {model} successfully")
    except Exception as e:
        print(f"WARNING: Download failed: {e}")
        print("ComfyUI will start but image generation won't work until model is downloaded.")
        print(f"Manual: huggingface-cli download {spec['repo_id']}")


def main() -> None:
    model = os.environ.get("IMAGE_MODEL", "flux-schnell")
    hf_token = os.environ.get("HF_TOKEN", "")
    models_dir = Path(os.environ.get("MODELS_DIR", "/models/checkpoints"))

    print(f"=== Portal 5: ComfyUI Model Download ===")
    print(f"Model: {model}")
    print(f"Destination: {models_dir}")
    print(f"HF_TOKEN: {'set' if hf_token else 'not set'}")
    print()

    try:
        download_model(model, hf_token, models_dir)
        print("\nDone. ComfyUI is ready for image generation.")
    except KeyboardInterrupt:
        print("\nDownload interrupted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
