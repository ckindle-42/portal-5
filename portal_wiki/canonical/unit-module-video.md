---
id: unit-module-video
kind: mixed
title: "Video Module \u2014 MLX-native video generation (off by default)"
sources:
- type: code
  path: portal/modules/media/tools/video_mlx_mcp.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
- type: code
  path: module-state-change:video:cli
claims:
- probe: modules.disabled
  contains: video
confidence: high
tags:
- video
- module
created_at: 1787967818.3609989
updated_at: 1787967818.3609989
---

# Video Module — MLX-native video generation (off by default)

## Tools

`video_mlx_mcp` (:8935) — a headless host-MLX wrapper over the `ltx-2-mlx`
CLI (pure-MLX LTX-2.3 port for Apple Silicon). Exposes `generate_video`
(text-to-video, with synchronized audio) and `animate_image`
(image-to-video). It replaced the removed ComfyUI `video_mcp` path — the
tool names are deliberately identical so the video workspace repoints with
a backend swap, not a tool-rename cascade.

## Workspaces

- `auto-video` — video creation

## Module State

The switch is `modules.video.enabled` in `config/portal.yaml` (`portal module enable|disable` writes it). This unit documents the switch; it does not hold it.

## Why

Video is the heaviest media surface — LTX-2.3 int4 runs a ~20-24GB MLX
working set, is thermally punishing on a 64GB box, and produces
preview-grade clips practically capped at ~4-6s — so it ships disabled
(`modules.video.enabled: false`). While it is off, sync-config drops the
`video_mlx` fleet id from `launched_mcp_ids` and the `auto-video` workspace
from the presets; `portal module enable video` restores both.
Membership comes from the `module: video` tag on the `video_mlx` fleet
entry and the `auto-video` workspace in `config/portal.yaml`. A missing
key falls back to `DEFAULT_DISABLED_MODULES` (off).
