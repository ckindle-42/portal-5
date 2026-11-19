---
id: unit-capability-mflux
kind: mixed
title: "MFLUX MCP \u2014 MLX-native image generation"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/media/tools/mflux_mcp.py
claims: []
confidence: high
tags:
- capability
- mcp
- image
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# MFLUX MCP — MLX-native image generation

## What

The MFLUX MCP (`portal/modules/media/tools/mflux_mcp.py`, port 8933) is a
headless wrapper over the per-family `mflux-generate-*` CLIs (mflux >=0.24.0) —
MLX-native for Apple Silicon. It is launched as a launchd service by
`./launch.sh install-mflux` and exposes an async surface: `image_start` returns
a job id immediately and `image_status(job_id)` long-polls (up to 20s per call)
for stage progress and the published download URL; `generate_image` /
`edit_image` remain as synchronous tools capped at `portal5/timeout_s: 900`
because a chat request's `request_timeout` is 300s.

## How it's used

`generate_image` and `image_start` take a `model` argument selecting
`flux2-klein` (FLUX.2 klein 4B, fast 4-step default, Apache 2.0), `flux3-klein`
(FLUX 3 Image Klein, 16-step distilled, quality / multi-reference, Kommunity
license), `qwen-2.1` (Qwen-Image-2.1-turbo, 8 steps, typography + instruction
editing, Qwen Research license), or `z-image` (Z-Image-Turbo, 8 steps, Apache
2.0 photoreal fallback). `edit_image` runs the family's `*-edit` binary with
repeatable `--image-paths`. `./launch.sh pull-mflux-models` pre-pulls the
weights per family binary (flux2-klein-4b ~15 GB, flux3-image-klein ~20 GB,
qwen-image-2.1-turbo ~33 GB, z-image-turbo ~21 GB). Every job passes a
`mflux:<model>` key to the Tier-1 admission check, which asks the Pipeline to
evict idle LLM residents before refusing.

## Why it exists

Image generation moved from a ComfyUI path to the host MLX layer because
Metal has no FP8, so ComfyUI's standard quantized checkpoints never ran here.
MFLUX is the MLX-native replacement, and keeping the `generate_image` /
`edit_image` names identical to the removed ComfyUI tools means the image
workspace repoints with a backend swap, not a tool-rename cascade.

## Value

FLUX-class image generation runs entirely on the local Metal accelerator with
no cloud round-trip. The async start/long-poll surface keeps multi-minute jobs
inside the 20-hop tool loop without blocking a chat request, and the model
switch lets a prompt pick the trade-off between speed, fidelity, licensing and
typography without changing anything else in the call.
