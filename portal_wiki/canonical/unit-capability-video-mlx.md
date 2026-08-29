---
id: unit-capability-video-mlx
kind: mixed
title: "Video-MLX MCP \u2014 MLX-native video generation"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/media/tools/video_mlx_mcp.py
- type: code
  path: config/inference/tools_manifest_video_mlx_mcp.json
claims: []
confidence: high
tags:
- capability
- mcp
- video
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Video-MLX MCP — MLX-native video generation

## What

The Video-MLX MCP (`portal/modules/media/tools/video_mlx_mcp.py`, port 8935)
is a headless host-MLX wrapper over the `ltx-2-mlx` CLI — a pure-MLX LTX-2.3
port for Apple Silicon. It exposes `generate_video` (text-to-video with
synchronized audio) and `animate_image` (image-to-video), installed by
`./launch.sh install-video-mlx` and launched by `start-video-mlx`.

## How it's used

The `video_mlx` fleet id belongs to the `video` module: disabled by default,
shipped enabled, and routed to the `auto-video` workspace, whose tools are
`generate_video` / `animate_image`. The model swap is deliberate — the tool
names are identical to the removed ComfyUI `video_mcp` path so the workspace
repoints with a backend swap, not a rename cascade.

## Why it exists

LTX-2.3 is the heaviest media surface in the platform — an int4 working set of
roughly 20-24 GB that is thermally punishing on a 64 GB box and produces
preview-grade clips practically capped at ~4-6 seconds. Footprint-first design
is why the default is off while the shipped build is on: a tight-footprint box
can disable the module without touching any other media path.

## Value

Video generation joins image, speech, transcription, and embeddings on a single
local MLX accelerator path — no Docker-to-Metal bridge and no cloud dependency.
Because it is a toggleable module behind one workspace, an operator pays the
memory cost only when the surface is actually used.
