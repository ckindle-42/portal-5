---
id: unit-capability-music-minimax
kind: mixed
title: "Music MCP \u2014 MiniMax full-song generation"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/media/tools/music_minimax_mcp.py
- type: code
  path: portal/modules/media/tools/music_ace_mcp.py
- type: code
  path: config/inference/tools_manifest_music_minimax_mcp.json
claims: []
confidence: high
tags:
- capability
- mcp
- media
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Music MCP — MiniMax full-song generation

## What

The Music MCP (`portal/modules/media/tools/music_minimax_mcp.py`, port 8912)
wraps the MiniMax Music-01 API for job-based full-song generation. It is
pipeline-exposed and IDE-exposed, serving the `auto-music` workspace. It is one
of two music backends; the retired ACE backend's tool surface was folded into
this server, so a workspace that once called `ace_generate` now calls the
MiniMax equivalents.

## How it's used

`minimax_generate` starts a song job from a prompt (with optional lyrics and a
duration), `minimax_status` polls that job to completion, and `minimax_models`
lists the available capability/availability surface. Because generation is
job-based, the workspace workflow is start-then-poll rather than a single
synchronous call.

## Why it exists

Full-song generation with lyrics and structure is a heavier, slower operation
than a TTS clip, so the backend is inherently asynchronous. Keeping the music
surface on one MCP with a start/poll contract means the model drop-down sees one
stable tool family regardless of which upstream engine actually renders the
track, and the workspace model (`lfm2.5`) routes the request without knowing
the backend's implementation details.

## Value

The auto-music workspace produces complete songs — verse, chorus, structure —
from a natural-language brief, with the two-step job surface giving an agent a
deterministic way to wait for a result that takes far longer than a chat turn.
The backend isolation means an engine swap changes nothing for a persona.
