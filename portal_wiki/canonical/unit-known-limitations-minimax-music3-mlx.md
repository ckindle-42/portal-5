---
id: unit-known-limitations-minimax-music3-mlx
kind: mixed
title: "Known Limitation — MiniMax-Music3-MLX Constraints"
sources:
- type: code
  path: portal/modules/media/tools/music_minimax_mcp.py
claims: []
confidence: high
tags: [known-limitations, music, apple-silicon]
created_at: 1787857994
updated_at: 1787857994
---

### MiniMax-Music3-MLX Apple-Silicon-Only, No Continuation, Community License

- **ID**: P5-MUSIC-MINIMAX-001
- **Description**: `music_minimax_mcp.py` uses PocketAiHub/MiniMax-Music3-MLX, a native MLX port with no CPU/CUDA/Linux fallback. Batch size is one. It has no clip-editing or continuation capability.
- **Impact**: This engine is unavailable off Apple Silicon. Output falls under the MiniMax-Music3 Community License, including its commercial attribution and revenue conditions.
- **Mitigation**: ACE-Step covers editing/continuation and has a PyTorch fallback. `_launch_install_music_minimax` refuses non-arm64 installs.

## Why

The architecture and license constraints need to remain visible at operation time because both can turn an otherwise successful local install into an unusable or non-compliant deployment. Keeping them in the generated register makes hardware eligibility and output obligations reviewable before an operator commits to this backend.
