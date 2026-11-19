---
id: unit-HOWTO-10-music-generation
kind: why
title: "HOWTO — 10. Music Generation"
sources:
- type: code
  path: portal/modules/media/tools/music_mcp.py
- type: code
  path: scripts/lib/services.sh
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.8455648
updated_at: 1787872869
---

**What:** Generate full songs — lyrics/vocals or instrumental — from text. The primary engine is ACE-Step 1.5 XL-Turbo. MiniMax-Music3 8-bit is the selectable fallback.

**Activate:** `./launch.sh install-music`, then `portal module enable music` and `./launch.sh sync-config`. Select `auto-audio::music` (alias `auto-music` through 2026-12-31). Tools: `music_start`, `music_status`, `music_models`, plus speech and transcription.

**How:** `music_mcp.py` (port 8912) does not hold weights. `music_start` admits memory, then spawns `music_worker`. Poll `music_status(job_id)` — the call waits on the server. Default engine `acestep` is 8 steps and up to 600 seconds (tool default 30). `engine=minimax` is 30 steps and up to 300 seconds. Lyrics use `[Verse]`/`[Chorus]` or `[Instrumental]`. `task_type` is `text2music`, `repaint`, `cover`, or `extend`. Edits need `source`. Output is a wav in `generated/music`.

**What changed:** The PocketAiHub MiniMax in-process server and the ACE-Step proxy plus `acestep-api` pair are gone. One host-native MCP remains, and the module still ships disabled. The 2026-08-27 dual-daemon comparison (2B sft, two launchd jobs, ~23–40 GB) does not describe this path. Peak RAM, speed, and AudioBox scores for XL-Turbo on this host are unmeasured.

## Why

A subprocess per job is how idle RAM returns: the child exits and the MCP stays small. Long-poll exists because a song outlasts one chat hop. The module stays off until the operator installs the pinned checkout and enables it on purpose.
