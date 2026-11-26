---
id: unit-capability-music
kind: mixed
title: "Music MCP \u2014 ACE-Step full-song generation"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/media/tools/music_mcp.py
- type: code
  path: portal/modules/media/tools/music_worker.py
claims:
- probe: repo.symbol.exists
  path: portal/modules/media/tools/music_mcp.py
  symbol: music_start
  equals: true
confidence: high
tags:
- capability
- mcp
- media
---

# Music MCP — ACE-Step full-song generation

## What

The Music MCP (`portal/modules/media/tools/music_mcp.py`, port 8912, fleet id
`music`) starts one subprocess per song (`music_worker.py`) so Metal memory
dies with the child. The primary engine is ACE-Step 1.5 XL-Turbo. Pass
`engine=minimax` for MiniMax-Music3 8-bit (`mlx-community/MiniMax-Music3-8bit`).
It is pipeline-exposed and IDE-exposed, gated by the `music` module (`unit-fact-module-states`).

## How it's used

`music_start` returns a `job_id` immediately. End that chat turn, then use
`music_status(job_id, wait_s=20)` in a later turn for progress or the wav under
`${AI_OUTPUT_DIR}/generated/music`. `music_models`
reports which engine install is present. ACE-Step accepts `task_type`
`text2music`, `repaint`, `cover`, or `extend` (`extend` is upstream
`complete`) plus `seed`. Repaint, cover, and extend take `source` as an upload
name or a `.wav` basename already in `generated/music`.

## Why it exists

Full-song generation is slower than a chat turn, and the previous in-process
MiniMax pipeline held its weights until the MCP process exited. Separate start
and status turns keep the chat request short, and the subprocess is the idle
release.

## Value

`auto-audio::music` can ask for a song, receive a job id, and poll for its
published file later. Memory admission (`music:acestep-xl-turbo` 16 GB estimate,
`music:minimax3-8bit` 22 GB — main's live MiniMax-Music3 family measurement,
carried over until the 8-bit card is sampled; XL-Turbo remains a research
estimate) runs before the child loads weights.
