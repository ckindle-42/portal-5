---
id: unit-module-music
kind: mixed
title: "Music Module — MiniMax song generation (off by default)"
sources:
- type: code
  path: portal/modules/media/tools/music_minimax_mcp.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
claims:
- probe: modules.disabled
  contains: music
confidence: high
tags:
- music
- module
---

# Music Module — MiniMax song generation (off by default)

## Tools

`music_minimax_mcp` (:8912, song generation). `music_ace_mcp` remains unwired
code under `portal/modules/media/tools/` (ACE-Step disabled 2026-08-27). TTS
and transcription stay on `unit-module-media`.

## Workspaces

- `auto-music` — music generation. Its tool list still includes `speak` and
  `transcribe_audio`; those servers launch with `media`, which stays enabled.

## Module State

The switch is `modules.music.enabled` in `config/portal.yaml` (`portal module enable|disable` writes it). This unit documents the switch; it does not hold it.

## Why

Song generation used to share the media toggle with TTS and transcription,
so music could not be turned off alone. It is its own module and ships
disabled. Membership comes from the `module: music` tag on `music-minimax`
and `auto-music` in `config/portal.yaml`. A missing `modules.music` key
falls back to `DEFAULT_DISABLED_MODULES` (off). `default_enabled: false` on
the fleet entry marks the server expected-down while the module is off.
No persona binds `auto-music`.
