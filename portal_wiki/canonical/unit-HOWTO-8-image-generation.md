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

**What:** Generate and edit images with MLX-native MFLUX — `flux2-klein` (fast 4-step default, Apache 2.0), `flux3-klein` (16-step quality / multi-reference), `qwen-2.1` (2.1-turbo, best for legible text and instruction edits), `z-image` (permissive photoreal fallback).

**Activate:** `./launch.sh install-mflux` installs the MFLUX MCP as a host-native launchd service on port 8933 (Apple Silicon only — a Docker container cannot reach the Metal GPU; pinned `mflux==0.24.0` on Python >=3.11). `./launch.sh pull-mflux-models` pre-pulls the weights through each family binary. The `auto-audio::image` workspace (`Portal Image Creator`) grants `generate_image` / `edit_image` / `image_start` / `image_status`; `auto-vision` grants the same image tools.

**How:** `portal/modules/media/tools/mflux_mcp.py` shells out to the `mflux-generate-*` family CLIs (`mflux-generate-flux2`, `-flux3`, `-qwen-2.1`, `-z-image-turbo`, and their `*-edit` variants). Call `image_start(prompt, model, …)` for anything multi-minute — it returns a job id immediately, and `image_status(job_id)` long-polls up to 20s per call for stage progress and the finished `{PORTAL_PUBLIC_URL}/api/v1/files/<id>/content/<name>` download URL, so the 20-hop tool loop covers minutes of generation. `generate_image(prompt, model, width, height, steps, seed)` stays synchronous (900s budget) for quick jobs. `edit_image(image_url, prompt, model)` does instruction editing through the family's `*-edit` binary with repeatable `--image-paths`; `image_url` is a public http(s) URL or an already-uploaded file name (SSRF-gated by `assert_public_http_url`). Every job passes a `mflux:<model>` key through the Tier-1 admission check, which asks the Pipeline's `/admin/reclaim-idle` to evict idle LLM residents before refusing. Outputs land in `generated/images/` and publish through Open WebUI's files API. Peaks: `flux2-klein` ~18 GB (measured), `flux3-klein` ~23 GB and `qwen-2.1` ~26 GB (sourced/reasoned bounds).

### Why

Image generation runs on the host MLX layer alongside speech/transcription/embeddings — one accelerator path, no Docker-to-Metal bridge, clean per-module removability. It replaced a ComfyUI-based path that could not run on this hardware (Metal has no FP8). The async start/long-poll surface keeps multi-minute jobs alive across the tool loop (the 60s dispatch kill and 20-hop cap no longer bite), and the admission check refuses an oversized job before it OOMs the 64 GB box.
