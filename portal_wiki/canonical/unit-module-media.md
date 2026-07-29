---
id: unit-module-media
kind: mixed
title: "Media Module \u2014 image/audio/speech generation"
sources:
- type: code
  path: portal/modules/media/
- type: design
  path: coding_task/BUILD_PROGRAM_MODULARIZATION_ALL_V1.md
- type: code
  path: module-state-change:media:cli
- type: code
  path: module-state-change:media:cli
last_generated_commit: ''
confidence: high
tags:
- module
- media
created_at: 1783895633.381192
updated_at: 1783895633.381192
---

# Media Module — image/audio/speech generation

## Tools

Active tools: `comfyui_mcp` (:8910, image), `music_mcp` (:8912,
host-native), `tts_mcp` (:8916), and `whisper_mcp` (:8915, STT).
`video_mcp` (:8911) is retained as archival code but disabled in normal
operation.

## Workspaces

- auto-audio
- auto-creative
- auto-image
- auto-music

## Module State

```yaml
enabled: true
```
