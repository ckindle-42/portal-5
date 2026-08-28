---
id: unit-fact-media-memory-budget
kind: what
title: memory budget for 9 media backend/model combinations
sources:
- type: code
  path: portal/platform/wiki/adapters/seed_facts.py
  commit: f5297714db3d
  section: MEDIA_MODEL_MEMORY_GB
claims: []
confidence: high
tags:
- fact
- media
- memory
created_at: 1784057641.950119
updated_at: 1787953098.848402
---

# Media backend memory budget (Tier 0, cross-engine VRAM admission)

Session-observed peak unified-memory estimates per media backend/model — no historical per-model table exists for ComfyUI/media (the retired MLX-proxy admission gate only covered the text/VLM inference tier). Used by the Tier 1 pre-flight admission check (`portal/modules/media/tools/_admission.py`) to refuse a job before it OOMs instead of after.

The `video:*` row is retained for the archived `video_mcp` code path; video service operation is shelved. Active ComfyUI operation is image-only.

| Backend:model | Estimated GB |
|---|---|
| `comfyui:flux-schnell` | 27.2 |
| `comfyui:qwen-image-2512` | 38.0 |
| `comfyui:qwen-image-2512-lightning` | 39.0 |
| `comfyui:qwen-image-edit-2509` | 38.0 |
| `comfyui:qwen-image-edit-2511` | 60.0 |
| `comfyui:sdxl` | 6.5 |
| `music:acestep-sft` | 40.0 |
| `music:minimax3` | 22.0 |
| `video:wan21-nsfw` | 55.0 |

## Why

The budget is the `MEDIA_MODEL_MEMORY_GB` table in this seeder, the session-observed peak unified-memory estimate the Tier-1 admission check in `_admission.py` consults to refuse a media job before it OOMs. Keeping it here rather than in a runtime config makes the numbers part of the reviewed, versioned wiki instead of an unreviewed setting.
