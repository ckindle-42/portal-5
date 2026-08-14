---
id: unit-module-media
kind: mixed
title: "Media Module \u2014 image/audio/speech generation"
sources:
- type: code
  path: portal/modules/media/tools/comfyui_mcp.py
- type: code
  path: portal/modules/media/tools/video_mcp.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
- type: code
  path: module-state-change:media:cli
last_generated_commit: 64c5f5f41652bf67e97863ee1a6285289eaeea00
claims: []
confidence: high
tags:
- media
- module
- verified-v1
created_at: 1783895633.381192
updated_at: 1783895633.381192
---

# Media Module — image/audio/speech generation

## Tools

Active tools: `comfyui_mcp` (:8910, image), `music_mcp` (:8912,
host-native), `tts_mcp` (:8916), and `whisper_mcp` (:8915, STT).
`video_mcp` (:8911) is retained as archival code but disabled in normal
operation — video generation is shelved and its fleet registration is
removed from `config/portal.yaml` `mcp_fleet:`, while the service
definition stays in `deploy/portal-5/docker-compose.yml`.

## Workspaces

- `auto-audio` — audio analysis
- `auto-creative` — creative writing
- `auto-image` — image creation
- `auto-music` — music generation

## Module State

```yaml
enabled: true
```

## Why

The media module's toggle gates four fleet ids (`comfyui`, `music`,
`tts`, `whisper`) and four workspaces, making it the highest-blast-radius
media surface; `video` is intentionally not part of that surface while
shelved. The fenced `enabled:` value is read as live config by
`portal/platform/wiki/adapters/modules.py` (`_unit_enabled_state`), and
the current true state was written by the module CLI — recorded as the
`module-state-change:media:cli` provenance source preserved on this unit.
Ports and fleet ids are grounded to `config/portal.yaml`; the archival
`video_mcp` lives on as code that is not registered.
