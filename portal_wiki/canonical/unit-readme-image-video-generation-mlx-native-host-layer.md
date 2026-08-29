---
id: unit-readme-image-video-generation-mlx-native-host-layer
kind: what
title: "README \u2014 Image / video generation (MLX-native, host layer)"
sources:
- type: code
  path: portal/modules/media/tools/mflux_mcp.py
- type: code
  path: portal/modules/media/tools/video_mlx_mcp.py
- type: code
  path: scripts/lib/services.sh
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1788033019.601702
updated_at: 1788033019.601702
---

Image generation is the **MFLUX MCP** (`portal/modules/media/tools/mflux_mcp.py`,
port 8933) — a headless wrapper over the `mflux-generate` CLI (MLX-native FLUX
for Apple Silicon). `./launch.sh install-mflux` sets it up as a launchd service;
`./launch.sh pull-mflux-models` pre-pulls the weights (FLUX.1-schnell full
weights are ~34 GB one-time). The `generate_image` tool takes a `model` arg:
`schnell` (fast default), `klein` (FLUX.2, higher quality), `qwen-image` (best
for legible text in the image), `dev`. `edit_image` does instruction editing
(`qwen-image-edit`) or img2img. Measured MLX peaks: `schnell` ~14.5 GB, `klein`
~18 GB.

Video generation is the **video-mlx MCP** (`video_mlx_mcp.py`, port 8935), a
wrapper over `ltx-2-mlx` (pure-MLX LTX-2.3). It is behind the `video` M7 module
— **off by default, shipped enabled** — installed with
`./launch.sh install-video-mlx` (and toggled with `portal module enable` /
`disable video`). Clips are preview-grade and practically capped at
~4–6 seconds on this hardware.

Both replaced a ComfyUI-based path removed in `TASK_IMAGE_VIDEO_OVERHAUL_V1`:
Metal has no FP8, so ComfyUI's standard quantized checkpoints never ran here.

## Why

Image and video generation run on the host MLX layer alongside
speech/transcription/embeddings — one accelerator path, no Docker-to-Metal
bridge, and each is its own toggleable module so a tight-footprint box can
disable the heavy `video` surface (or image generation) without losing the
audio media. Weights download on demand via `install-*` / `pull-*` so the
operator pays the cost only for the models actually used.
