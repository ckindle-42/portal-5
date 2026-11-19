---
id: unit-module-music
kind: mixed
title: "Music Module \u2014 ACE-Step song generation"
sources:
- type: code
  path: portal/modules/media/tools/music_mcp.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- music
- module
---

# Music Module — ACE-Step song generation
## Tools

`music_mcp` (:8912, launchd `com.portal5.music`) exposes `music_start`,
`music_status`, and `music_models`. The default engine is ACE-Step 1.5
XL-Turbo (`use_mlx_dit`, 8 steps, 48 kHz). `engine=minimax` selects
MiniMax-Music3 8-bit through mlx-audio. Each job is a subprocess that exits
when the wav is written under `generated/music`. TTS and transcription stay
on `unit-module-media`.

## Workspaces

- `auto-audio::music` — song generation. The alias `auto-music` stays through
  2026-12-31. Its tool list still includes `speak` and `transcribe_audio`;
  those servers launch with `media`, which stays enabled.

## Module State

The switch is `modules.music.enabled` in `config/portal.yaml` (`portal module enable|disable` writes it). This unit documents the switch; it does not hold it.

## Why

Song generation used to share the media toggle with TTS and transcription,
so music could not be turned off alone. It is its own module; query `unit-fact-module-states` for live enablement. Membership comes from the `module: music` tag on fleet id `music`
and `auto-audio::music` in `config/portal.yaml`. A missing `modules.music`
key falls back to `DEFAULT_DISABLED_MODULES` (off). `default_enabled: false`
on the fleet entry marks the server expected-down when the module is disabled.
No persona binds `auto-audio::music`. Install with `./launch.sh install-music`
before enabling.
