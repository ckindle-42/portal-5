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
- probe: modules.enabled
  contains: video
confidence: high
tags:
- video
- module

---

# Video Module — MLX-native video generation (off by default)

## Tools

`video_mlx_mcp` (:8935) — a headless host-MLX wrapper over the `ltx-2-mlx`
CLI (pure-MLX LTX-2.5 for Apple Silicon) with an opt-in `mlx-video`
Wan2.2-TI2V-5B fallback. Exposes the async job contract: `video_start`
(text-to-video, or image-to-video via `image_url`; returns a job id),
`video_status` (server-side long-poll until the job finishes), and
`video_models` (the roster). It replaced the removed ComfyUI `video_mcp`
path.

## Workspaces

- `auto-audio::video` — video creation (the `auto-video` alias keeps working
  through its 2026-12-31 deprecation window)

## Module State

The switch is `modules.video.enabled` in `config/portal.yaml` (`portal module enable|disable` writes it). This unit documents the switch; it does not hold it. `portal module disable video --yes` bootouts `com.portal5.video-mlx`; `enable --yes` bootstraps and kickstarts it. `./launch.sh up` does the same from the module→service map.

## Why

Video is the heaviest media surface — LTX-2.5 int4 runs an 18-26GB MLX
working set, is thermally punishing on a 64GB box, and produces
preview-grade clips practically capped at ~4-6s — it shipped disabled; it is now enabled
(`modules.video.enabled: true` since 2026-11-19, live trace PASS; peak worker ~9 GB, free memory ≥52%). When it is off, sync-config drops the
`video_mlx` fleet id from `launched_mcp_ids` and the `auto-audio::video`
workspace from the presets; `portal module enable video` restores both.
Membership comes from the `module: video` tag on the `video_mlx` fleet
entry and the `auto-audio::video` workspace in `config/portal.yaml`. A missing
key falls back to `DEFAULT_DISABLED_MODULES` (off).
