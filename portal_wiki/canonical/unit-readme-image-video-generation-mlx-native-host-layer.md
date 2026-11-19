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
claims:
- probe: repo.path.exists
  path: portal/modules/media/tools/mflux_mcp.py
  equals: true
confidence: high
tags:
- docs
- verified-v1
---

Image generation is the **MFLUX MCP** (`portal/modules/media/tools/mflux_mcp.py`,
port 8933) — a headless wrapper over the per-family `mflux-generate-*` CLIs
(mflux >=0.24.0, MLX-native for Apple Silicon). `./launch.sh install-mflux` sets
it up as a launchd service (pinned `mflux==0.24.0`, Python >=3.11);
`./launch.sh pull-mflux-models` pre-pulls the weights (flux2-klein-4b ~15 GB,
flux3-image-klein ~20 GB, qwen-image-2.1-turbo ~33 GB, z-image-turbo ~21 GB).
`generate_image` / `image_start` take a `model` arg: `flux2-klein` (fast 4-step
default, Apache 2.0), `flux3-klein` (16-step quality / multi-ref),
`qwen-2.1` (2.1-turbo, typography + instruction edits), `z-image` (permissive
photoreal fallback). `edit_image` runs the family's `*-edit` binary
(`--image-paths`); jobs pass a `mflux:<model>` key to the Tier-1 admission
check, which asks the Pipeline to evict idle LLM residents before refusing.
Peaks: `flux2-klein` ~18 GB (measured), `flux3-klein` ~23 GB and `qwen-2.1`
~26 GB (sourced/reasoned bounds, see the memory-budget unit).

Video generation is the **video-mlx MCP** (`video_mlx_mcp.py`, port 8935), a
wrapper over `ltx-2-mlx` (pure-MLX LTX-2.5). It is behind the `video` M7 module (`unit-fact-module-states`), installed with
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
