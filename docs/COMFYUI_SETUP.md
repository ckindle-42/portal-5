# Portal 5.2 — ComfyUI Setup Guide

ComfyUI handles image and video generation. It runs natively on the host
for Metal GPU access on Apple Silicon.

## Quick Install (Apple Silicon)

```bash
./launch.sh install-comfyui
```

This clones ComfyUI to `~/ComfyUI`, installs PyTorch with MPS support,
and registers it as a launchd service that auto-starts on login.

## Download Models

```bash
# Default: flux-schnell (image) + wan2.2 (video)
./launch.sh download-comfyui-models

# Choose a different image model:
IMAGE_MODEL=flux-uncensored ./launch.sh download-comfyui-models

# All image model options:
#   flux-schnell (~12GB, default)    flux-dev (~24GB, needs HF_TOKEN)
#   flux-uncensored (~24GB)          flux2-klein (~20GB)
#   sdxl (~7GB)                      juggernaut-xl (~7GB)
#   pony-diffusion (~12GB)           epicrealism-xl (~12GB)

# All video model options:
#   wan2.2 (~18GB, default)          wan2.2-uncensored (~20GB)
#   skyreels-v1 (~15GB)              mochi-1 (~15GB)
#   stable-video-diffusion (~10GB)
```

## Manual Start / Stop

```bash
# Start
~/ComfyUI/start.sh

# Stop
launchctl stop com.portal5.comfyui

# Restart
launchctl stop com.portal5.comfyui && launchctl start com.portal5.comfyui

# View logs
tail -f ~/.portal5/logs/comfyui.log
```

## Linux (NVIDIA GPU)

```bash
# Use Docker ComfyUI with CUDA profile
./launch.sh up --profile docker-comfyui
# Models download automatically on first start
```

## Verify

```bash
curl http://localhost:8188/system_stats
# Should return JSON with GPU info showing MPS device
```