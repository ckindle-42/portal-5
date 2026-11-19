---
id: unit-known-limitations-minimax-music3-mlx
kind: mixed
title: "Known Limitation — MiniMax-Music3 8-bit fallback"
sources:
- type: code
  path: portal/modules/media/tools/music_worker.py
claims:
- probe: repo.symbol.exists
  path: portal/modules/media/tools/music_worker.py
  symbol: _minimax
  equals: true
confidence: high
tags: [known-limitations, music, apple-silicon]

---

### MiniMax-Music3 8-bit fallback — Apple Silicon, community license, text-to-music only

- **ID**: P5-MUSIC-MINIMAX-001
- **Description**: The MiniMax path is `engine=minimax` inside `music_worker.py`, loading `mlx-community/MiniMax-Music3-8bit` through `mlx_audio.music` (`mlx-audio==0.6.6`). It is not the retired PocketAiHub in-process pipeline. This engine accepts `text2music` only. Output falls under the MiniMax-Music3 Community License. Admission uses `music:minimax3-8bit` = 22 GB plus headroom — the live vm_stat peak measured for the retired PocketAiHub port of the same MiniMax-Music3 model, carried over from main; the 8-bit card itself is not yet sampled.
- **Impact**: Unavailable off Apple Silicon. Repaint, cover, and extend are ACE-Step tasks. The 8-bit card's audio quality on this host is unmeasured.
- **Mitigation**: `./launch.sh install-music` refuses non-arm64. Use the default `acestep` engine for edits.

## Why

The license and the hardware limit still decide whether a fallback take is usable. The carried-over measurement of the same model family is used until a local sample of the 8-bit card replaces it.
