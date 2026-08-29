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
- type: code
  path: config/inference/tools_manifest_mflux_mcp.json
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
headless wrapper over the `mflux-generate` CLI — MLX-native FLUX for Apple
Silicon. It is launched as a launchd service by `./launch.sh install-mflux`
and exposes `generate_image` and `edit_image` synchronously: a job finishes
inside the chat request, there is no start-and-poll surface.

## How it's used

`generate_image` takes a `model` argument selecting `schnell` (fast default),
`klein` (FLUX.2, higher quality), `qwen-image` (best for legible text in the
image), or `dev`; `edit_image` does instruction editing (`qwen-image-edit`) or
img2img. `./launch.sh pull-mflux-models` pre-pulls the weights (FLUX.1-schnell
full weights are ~34 GB one-time). Measured MLX peaks are ~14.5 GB for
`schnell` and ~18 GB for `klein`.

## Why it exists

Image generation moved from a ComfyUI path to the host MLX layer because
Metal has no FP8, so ComfyUI's standard quantized checkpoints never ran here.
MFLUX is the MLX-native replacement, and keeping the `generate_image` /
`edit_image` names identical to the removed ComfyUI tools means the image
workspace repoints with a backend swap, not a tool-rename cascade.

## Value

FLUX-class image generation runs entirely on the local Metal accelerator with
no cloud round-trip. The two-tool surface is synchronous and predictable, and
the model switch lets a prompt pick the trade-off between speed and fidelity
without changing anything else in the call.
