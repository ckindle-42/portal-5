---
id: unit-HOWTO-9-video-generation
kind: why
title: "HOWTO — 9. Video Generation"
sources:
- type: code
  path: portal/modules/media/tools/video_mlx_mcp.py
claims: []
confidence: high
tags:
- HOWTO
- docs
---

**What:** Generate short clips (with synchronized audio) from a text prompt or animate a still image, via MLX-native LTX-2.3.

**Off by default, shipped enabled:** the `video` module ships enabled in the default config — `auto-video` is exposed to Open WebUI, the `video_mlx` fleet entry (port 8935) is registered, and `sync-config` keeps both in the presets. What stays off by default is the engine: LTX-2.3 is a host-native MLX install (Apple Silicon only, no Docker-to-Metal bridge) that a fresh box lacks until `./launch.sh install-video-mlx` (clones `dgrauet/ltx-2-mlx`, `uv sync`) and `./launch.sh start-video-mlx` are run. It runs a large MLX working set, is thermally punishing on a 64 GB box, and produces preview-grade clips practically capped at ~4–6 s.

**How:** `portal/modules/media/tools/video_mlx_mcp.py` shells out to `ltx-2-mlx generate --distilled --low-ram`. `generate_video(prompt, model, frames, width, height, seed)` (frames snap to the LTX `8k+1` constraint) and `animate_image(image_url, prompt, ...)` (i2v). Model packs: `ltx-2.3-q4` (int4) / `ltx-2.3-q8` (int8). Jobs run several minutes; a `video_mlx:<model>` admission key gates each one. Output is an mp4 published through Open WebUI's files API.

## Why

Video is the heaviest media surface, so the engine install stays footprint-first — off until an operator opts in — even though the module itself ships enabled so the workspace, fleet entry, and routing are present by default. Keeping it a real module rather than deleted code means enabling is a one-command toggle, not a rebuild.
