---
id: unit-capability-music
kind: mixed
title: "Music MCP — ACE-Step full-song generation"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/media/tools/music_mcp.py
- type: code
  path: portal/modules/media/tools/music_worker.py
claims: []
confidence: high
tags:
- capability
- mcp
- media
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Music MCP — ACE-Step full-song generation

## What

The Music MCP (`portal/modules/media/tools/music_mcp.py`, port 8912, fleet id
`music`) starts one subprocess per song (`music_worker.py`) so Metal memory
dies with the child. The primary engine is ACE-Step 1.5 XL-Turbo. Pass
`engine=minimax` for MiniMax-Music3 8-bit (`mlx-community/MiniMax-Music3-8bit`).
It is pipeline-exposed and IDE-exposed. The module ships disabled.

## How it's used

`music_start` returns a `job_id`. `music_status(job_id)` long-polls for
progress or the wav under `${AI_OUTPUT_DIR}/generated/music`. `music_models`
reports which engine install is present. ACE-Step accepts `task_type`
`text2music`, `repaint`, `cover`, or `extend` (`extend` is upstream
`complete`) plus `seed`. Repaint, cover, and extend take `source` as an upload
name or a `.wav` basename already in `generated/music`.

## Why it exists

Full-song generation is slower than a chat turn, and the previous in-process
MiniMax pipeline held its weights until the MCP process exited. A start plus
long-poll contract keeps `MAX_TOOL_HOPS` from burning a poll per second, and
the subprocess is the idle release.

## Value

`auto-audio::music` can ask for a song and get a file path back from one
status call. Memory admission (`music:acestep-xl-turbo` 16 GB estimate,
`music:minimax3-8bit` 18 GB estimate, plus headroom) runs before the child
loads weights. Those gigabyte figures are research estimates, not live samples.
