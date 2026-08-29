---
id: unit-capability-tts
kind: mixed
title: "TTS MCP \u2014 speech synthesis and voice cloning"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: config/inference/tools_manifest_tts_mcp.json
claims: []
confidence: high
tags:
- capability
- mcp
- media
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# TTS MCP — speech synthesis and voice cloning

## What

The TTS MCP (`portal/modules/media/tools/tts_mcp.py`, port 8916) turns text
into spoken audio via the host MLX speech server. It is pipeline- and
IDE-exposed and serves the `auto-music` workspace's narration tools as well as
any persona that needs speech output.

## How it's used

`speak` synthesizes text in a named voice (Kokoro preset like `af_heart`, a
registered trainer voice, or a one-off clone) and returns a downloadable audio
link. `list_voices` enumerates the built-in and registered voices;
`clone_voice` speaks text in a voice cloned from a reference clip;
`register_voice` persists a trainer voice so later sessions narrate in it via
the `trainer:` prefix.

## Why it exists

Speech is latency-sensitive and the underlying MLX server is host-native
precisely to keep synthesis fast with models loaded once. The TTS MCP is the
typed, persona-callable front door to that server — it owns the voice
vocabulary and the cloning surface while the heavy MLX work stays on the host.

## Value

A persona can narrate a training session, read a briefing aloud, or clone a
specific voice without knowing the MLX server's internals. Because voices are
addressed by stable names, a cloned trainer voice persists across sessions and
feels like a first-class identity rather than a per-call artifact.
