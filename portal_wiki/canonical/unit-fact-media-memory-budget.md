---
id: unit-fact-media-memory-budget
kind: what
title: memory budget for 10 media backend/model combinations
sources:
- type: code
  path: portal/platform/wiki/adapters/seed_facts.py
  commit: 38cdbb1fcea0
  section: MEDIA_MODEL_MEMORY_GB
claims: []
confidence: high
tags:
- fact
- media
- memory
created_at: 1784057641.950119
updated_at: 1787966215.572633
---

# Media backend memory budget (Tier 0, cross-engine VRAM admission)

Session-observed peak unified-memory estimates per media backend/model. Used by the Tier 1 pre-flight admission check (`portal/modules/media/tools/_admission.py`) to refuse a job before it OOMs instead of after.

Image is `mflux:*` (MLX-native FLUX, host layer), video is `video_mlx:*` (ltx-2-mlx, host layer), music is `music:*`. All are measured MLX peaks with `--low-ram` / block streaming.

| Backend:model | Estimated GB |
|---|---|
| `mflux:dev` | 16.0 |
| `mflux:klein` | 18.0 |
| `mflux:qwen-image` | 40.0 |
| `mflux:qwen-image-edit` | 42.0 |
| `mflux:schnell` | 15.0 |
| `mflux:z-image` | 30.0 |
| `music:acestep-sft` | 40.0 |
| `music:minimax3` | 22.0 |
| `video_mlx:ltx-2.3-q4` | 18.0 |
| `video_mlx:ltx-2.3-q8` | 28.0 |

## Why

The budget is the `MEDIA_MODEL_MEMORY_GB` table in this seeder, the session-observed peak unified-memory estimate the Tier-1 admission check in `_admission.py` consults to refuse a media job before it OOMs. Keeping it here rather than in a runtime config makes the numbers part of the reviewed, versioned wiki instead of an unreviewed setting.
