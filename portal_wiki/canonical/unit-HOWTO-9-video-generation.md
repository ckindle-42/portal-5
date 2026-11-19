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

**What:** Generate short clips (with synchronized audio) from a text prompt or animate a still image, via MLX-native LTX-2.5 — or the opt-in Wan2.2-TI2V-5B fallback.

**Off by default:** the `video` module is disabled in the default config (`modules.video.enabled: false`) — `sync-config` drops the `auto-audio::video` workspace from the presets and the `video_mlx` fleet entry (port 8935) from `launched_mcp_ids` until `portal module enable video` flips it. What stays off even after that is the engine: LTX-2.5 is a host-native MLX install (Apple Silicon only, no Docker-to-Metal bridge) that a fresh box lacks until `./launch.sh install-video-mlx` (clones `dgrauet/ltx-2-mlx`, `uv sync`) and `./launch.sh start-video-mlx` are run. It runs an 18–26GB MLX working set, is thermally punishing on a 64 GB box, and produces preview-grade clips practically capped at ~4–6 s.

**How:** `video_start(prompt, model, width, height, frames, seed, fps, image_url, quality)` returns a job id immediately; `video_status(job_id)` long-polls up to ~20s per call, so the Pipeline's 20-hop tool loop covers a multi-minute render; `video_models()` lists the roster. Frames snap to the LTX `8k+1` grid. `quality='fast'` runs `--distilled`, `quality='hq'` runs the two-stage pass (TeaCache is upstream-2.3-only and is not exposed). Default pack `ltx-2.5-q4` (int4; replaced LTX-2.3 after the 2026-10-28 A/B); `wan2.2-5b` (mlx-video, silent MP4) is the opt-in Apache-2.0 fallback installed by `./launch.sh install-video-mlx wan`. Jobs run several minutes; a size-aware `video_mlx:ltx-2.5-q4-512|-704` admission key gates each one, and the Tier-1 check asks the Pipeline to evict idle LLM residents before refusing. The renderer is a subprocess per job, so Metal memory returns to macOS when it exits. Output is an mp4 under `${AI_OUTPUT_DIR}/generated/videos/` published through Open WebUI's files API.

## Why

Video is the heaviest media surface, so the engine install stays footprint-first — off until an operator opts in — even though the module's workspace, fleet entry, and routing are declared in config. Keeping it a real module rather than deleted code means enabling is a one-command toggle, not a rebuild.
