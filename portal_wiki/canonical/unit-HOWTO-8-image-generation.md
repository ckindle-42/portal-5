---
id: unit-HOWTO-8-image-generation
kind: why
title: "HOWTO — 8. Image Generation"
sources:
- type: code
  path: portal/modules/media/tools/mflux_mcp.py
claims: []
confidence: high
tags:
- HOWTO
- docs
---

**What:** Generate and edit images with MLX-native FLUX — `schnell` (fast default), `klein` (FLUX.2), `qwen-image` (best for legible text in the image).

**Activate:** `./launch.sh install-mflux` installs the MFLUX MCP as a host-native launchd service on port 8933 (Apple Silicon only — a Docker container cannot reach the Metal GPU). `./launch.sh pull-mflux-models` pre-pulls the weights. The `auto-image` workspace (`Portal Image Creator`) grants `generate_image` / `edit_image`; `auto-vision` also grants `generate_image`.

**How:** `portal/modules/media/tools/mflux_mcp.py` shells out to the `mflux-generate` / `mflux-generate-flux2` CLI. `generate_image(prompt, model, width, height, steps, seed)` is synchronous — a few seconds (`schnell`) to a couple of minutes (`klein` / `qwen-image`). `edit_image(image_url, prompt, model, strength)` does instruction editing (`qwen-image-edit`) or img2img; `image_url` is a public http(s) URL or an already-uploaded file name (SSRF-gated by `assert_public_http_url`). Every job passes a `mflux:<model>` key through the Tier-1 admission check. Outputs land in `generated/images/` and publish through Open WebUI's files API. Measured MLX peaks: `schnell` ~14.5 GB, `klein` ~18 GB (`--quantize 8 --low-ram`).

## Why

Image generation runs on the host MLX layer alongside speech/transcription/embeddings — one accelerator path, no Docker-to-Metal bridge, clean per-module removability. It replaced a ComfyUI-based path that could not run on this hardware (Metal has no FP8). The synchronous tool surface is enough because MFLUX jobs finish inside a chat request; the admission check refuses an oversized job before it OOMs the 64 GB box.
