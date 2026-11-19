---
id: unit-known-limitations-minimax-music3-mlx
kind: mixed
title: "Known Limitation — MiniMax-Music3 8-bit fallback"
sources:
- type: code
  path: portal/modules/media/tools/music_worker.py
claims: []
confidence: high
tags: [known-limitations, music, apple-silicon]
created_at: 1787857994
updated_at: 1787872869
---

### MiniMax-Music3 8-bit fallback — Apple Silicon, community license, text-to-music only

- **ID**: P5-MUSIC-MINIMAX-001
- **Description**: The MiniMax path is `engine=minimax` inside `music_worker.py`, loading `mlx-community/MiniMax-Music3-8bit` through `mlx_audio.music` (`mlx-audio==0.6.6`). It is not the retired PocketAiHub in-process pipeline. This engine accepts `text2music` only. Output falls under the MiniMax-Music3 Community License. Admission uses `music:minimax3-8bit` = 18 GB plus headroom, a research estimate.
- **Impact**: Unavailable off Apple Silicon. Repaint, cover, and extend are ACE-Step tasks. The 8-bit card's live peak RAM and audio quality on this host are unmeasured.
- **Mitigation**: `./launch.sh install-music` refuses non-arm64. Use the default `acestep` engine for edits.

## Why

The license and the hardware limit still decide whether a fallback take is usable. The estimate stays labeled as an estimate so it is not read as a measured peak.
