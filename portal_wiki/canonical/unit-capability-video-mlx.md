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
claims:
- probe: repo.path.exists
  path: config/portal.yaml
  equals: true
confidence: high
tags:
- capability
- mcp
- video
---

# Video-MLX MCP — MLX-native video generation

## What

The Video-MLX MCP (`portal/modules/media/tools/video_mlx_mcp.py`, port 8935)
is a headless host-MLX wrapper over the `ltx-2-mlx` CLI — a pure-MLX LTX-2.5
port for Apple Silicon — with an opt-in `mlx-video` Wan2.2-TI2V-5B fallback.
It exposes the async job contract: `video_start` (text- or image-to-video,
returns a job id), `video_status` (server-side long-poll), and `video_models`
(the roster), installed by `./launch.sh install-video-mlx` and launched by
`start-video-mlx`.

## How it's used

The `video_mlx` fleet id belongs to the `video` module (`unit-fact-module-states`,
`config/portal.yaml`), routed to the `auto-audio::video`
workspace (the `auto-video` alias retains live API callers through
2026-12-31), whose tools are `video_start` / `video_status`.

## Why it exists

LTX-2.5 is the heaviest media surface in the platform — an int4 working set
of roughly 18-26 GB that is thermally punishing on a 64 GB box and produces
preview-grade clips practically capped at ~4-6 seconds. Footprint-first
design is why the surface is a module toggle plus a separate engine install
(`unit-fact-module-states`): a tight-footprint box can leave the module
disabled without touching any other media path, and the renderer runs as a
subprocess per job so Metal memory returns to macOS between jobs.

## Value

Video generation joins image, speech, transcription, and embeddings on a single
local MLX accelerator path — no Docker-to-Metal bridge and no cloud dependency.
Because it is a toggleable module behind one workspace, an operator pays the
memory cost only when the surface is actually used.
