---
id: unit-HOWTO-10-music-generation
kind: why
title: "HOWTO — 10. Music Generation"
sources:
- type: code
  path: portal/modules/media/tools/music_minimax_mcp.py
- type: code
  path: portal/modules/media/tools/music_ace_mcp.py
- type: code
  path: scripts/lib/services.sh
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.8455648
updated_at: 1787857994
---

**What:** Generate full songs — with lyrics/vocals or instrumental — from text descriptions, using either of two music engines installed side by side for comparison: MiniMax-Music3-MLX and ACE-Step-1.5. ACE-Step additionally edits/extends existing clips (cover, repaint).

**Activate:** Select `Music Producer` (`auto-music`). Both engines' tools — `minimax_generate`/`minimax_status`/`minimax_models` and `ace_generate`/`ace_status`/`ace_models`, plus speech/transcription tools — are granted by `auto-music`'s `tools` list.

**How:** MiniMax runs in-process in `music_minimax_mcp.py` (port 8912) via the vendor's MLX pipeline. ACE-Step runs as its own host-native API server (`./launch.sh install-music-ace`, launchd `com.portal5.acestep-server`, port 8001), fronted by `music_ace_mcp.py` (port 8933). Both are job-based: call `*_generate` for a `job_id`, then poll `*_status(job_id)` until done. Complete-quality defaults are 60 seconds / 30 steps on both; ACE-Step uses the non-turbo `acestep-v15-sft` DiT with the 1.7B LM planner. Lyrics use `[Verse]`/`[Chorus]` tags or `[Instrumental]`. ACE-Step's `task_type="repaint"` regenerates/extends a time range; `task_type="cover"` does style transfer.

**What changed:** MusicGen was removed entirely and replaced with these two engines. Which one is kept long-term is an open operator decision.

## Why

Independent modules let either engine be removed without touching the other. ACE-Step's separate-server shape provides crash isolation and an independent upgrade path. Job polling exists because complete-quality generation takes minutes.
