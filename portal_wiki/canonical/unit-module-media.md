---
id: unit-module-media
kind: mixed
title: "Media Module — speech and transcription"
sources:
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
claims:
- probe: modules.enabled
  contains: media
confidence: high
tags:
- media
- module
- verified-v1

---

# Media Module — speech and transcription

## Tools

Active tools: `tts_mcp` (:8916, text-to-speech) and `whisper_mcp` (:8915,
STT). Song generation is `unit-module-music` (`music_mcp`, :8912, module off).
Image generation and video
generation are their own modules — `unit-module-image` (`mflux`, :8933) and
`unit-module-video` (`video_mlx`, :8935).

## Workspaces

- `auto-audio` — audio analysis
- `auto-creative` — creative writing

## Module State

The switch is `modules.media.enabled` in `config/portal.yaml` (`portal module enable|disable` writes it). This unit documents the switch; it does not hold it.

## Why

The media toggle gates `tts` and `whisper` and the audio workspaces.
Song generation is `music`, and image and video generation are their own
modules, so each heavy surface can be off while speech and transcription
stay on. `modules.media.enabled` in `config/portal.yaml` is the switch.
Ports and fleet ids are grounded to that file.
