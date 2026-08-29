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

**Off by default:** the `video` M7 module is disabled by default — LTX-2.3 runs a large MLX working set, is thermally punishing on a 64 GB box, and produces preview-grade clips practically capped at ~4–6 s. Enable with `./launch.sh install-video-mlx` (clones `dgrauet/ltx-2-mlx`, `uv sync`) then `portal module enable video`; `sync-config` then adds the `video_mlx` fleet id and the `auto-video` workspace to the presets.

**How:** `portal/modules/media/tools/video_mlx_mcp.py` shells out to `ltx-2-mlx generate --distilled --low-ram`. `generate_video(prompt, model, frames, width, height, seed)` (frames snap to the LTX `8k+1` constraint) and `animate_image(image_url, prompt, ...)` (i2v). Model packs: `ltx-2.3-q4` (int4) / `ltx-2.3-q8` (int8). Jobs run several minutes; a `video_mlx:<model>` admission key gates each one. Output is an mp4 published through Open WebUI's files API.

## Why

Video is the heaviest media surface, so it is footprint-first — off unless an operator opts in, mirroring the `eval` module. Keeping it a real (if disabled) module rather than deleted code means enabling it is a one-command toggle, not a rebuild.
