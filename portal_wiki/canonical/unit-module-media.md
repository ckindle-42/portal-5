---
id: unit-module-media
kind: mixed
title: "Media Module — audio/music/speech generation"
sources:
- type: code
  path: portal/modules/media/tools/music_minimax_mcp.py
- type: code
  path: portal/modules/media/tools/music_ace_mcp.py
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: portal/modules/media/tools/whisper_mcp.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
- type: code
  path: module-state-change:media:cli
claims: []
confidence: high
tags:
- media
- module
- verified-v1
created_at: 1783895633.381192
updated_at: 1787857994
---

# Media Module — audio/music/speech generation

## Tools

Active tools: `music_minimax_mcp` (:8912, song generation), `tts_mcp` (:8916,
text-to-speech), and `whisper_mcp` (:8915, STT). `music_ace_mcp` is retained as
unwired code (ACE-Step disabled 2026-08-27 after the operator's engine-select
gate). Image generation and video generation are their own modules now —
`unit-module-image` (`mflux`, :8933) and `unit-module-video` (`video_mlx`,
:8935) — not part of the media toggle.

## Workspaces

- `auto-audio` — audio analysis
- `auto-creative` — creative writing
- `auto-music` — music generation

## Module State

```yaml
enabled: true
```

## Why

The media module's toggle gates the music/tts/whisper fleet ids and the
audio workspaces. Image and video generation were split out into their own
modules (`image`, `video`) so a tight-footprint box can disable the heavy
video surface — or image generation — without losing the audio media. The
fenced `enabled:` value is read as live config by
`portal/platform/wiki/adapters/modules.py` (`_unit_enabled_state`), and the
current true state was written by the module CLI — recorded as the
`module-state-change:media:cli` provenance source preserved on this unit.
Ports and fleet ids are grounded to `config/portal.yaml`.
