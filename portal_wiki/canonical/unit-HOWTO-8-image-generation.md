---
id: unit-HOWTO-8-image-generation
kind: why
title: "HOWTO \u2014 8. Image Generation"
sources:
- type: code
  path: portal/modules/media/tools/comfyui_mcp.py
last_generated_commit: 9623f6b25b3e922bd0cf4b3885a926a4728b26a1
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.84399
updated_at: 1783195000.84399
---

**What:** Generate images using ComfyUI — FLUX, SDXL, and Qwen-Image checkpoints.

**Activate:** ComfyUI runs natively on the host (`./launch.sh install-comfyui`, installed into `COMFYUI_DIR`, served at `http://localhost:8188`) because a Docker container cannot reach the Metal GPU. The `mcp-comfyui` container (port 8910) exposes the `generate_image` / `start_image_generation` tools to models, and the `auto-image` workspace (`Portal Image Creator`) grants them, so selecting that workspace makes image generation available.

**How:** `portal/modules/media/tools/comfyui_mcp.py` drives ComfyUI's workflow API. The default `flux` model maps to the `comfyui:flux-schnell` checkpoint; `sdxl`, `qwen-image-2512`, and the `qwen-image-edit-*` editing models are selectable per call. Jobs can take minutes, so the tool surface splits into a blocking `generate_image` and the async `start_image_generation` + `get_image_status` pair. Outputs land in the shared workspace `generated/images/` and the MCP returns a URL. `.env` sets `COMFYUI_URL` and the `COMFYUI_TIMEOUT` ceiling. See `docs/COMFYUI_SETUP.md` for the full setup.

## Why

Image generation is split across two processes by hardware reality: ComfyUI must run on the host to use MPS, while the MCP bridge keeps the model-facing tool API uniform. The async job surface exists because diffusion jobs routinely outlast a chat request timeout, so models are taught to start a job, return the id, and poll rather than block.
