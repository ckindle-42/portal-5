---
id: unit-fact-media-memory-budget
kind: what
title: memory budget for 9 media backend/model combinations
sources:
- type: code
  path: portal/platform/wiki/adapters/seed_facts.py
  commit: 1396e41bf4cc
  section: MEDIA_MODEL_MEMORY_GB
last_generated_commit: 1396e41bf4cc
confidence: high
tags:
- fact
- media
- memory
created_at: 1784057641.950119
updated_at: 1785302097.576195
---

# Media backend memory budget (Tier 0, cross-engine VRAM admission)

Session-observed peak unified-memory estimates per media backend/model — no historical per-model table exists for ComfyUI/media (the retired MLX-proxy admission gate only covered the text/VLM inference tier). Used by the Tier 1 pre-flight admission check (`portal/modules/media/tools/_admission.py`) to refuse a job before it OOMs instead of after.

| Backend:model | Estimated GB |
|---|---|
| `comfyui:flux-schnell` | 27.2 |
| `comfyui:qwen-image-2512` | 38.0 |
| `comfyui:qwen-image-2512-lightning` | 39.0 |
| `comfyui:qwen-image-edit-2511` | 60.0 |
| `comfyui:sdxl` | 6.5 |
| `music:large` | 12.0 |
| `music:medium` | 6.0 |
| `music:small` | 2.0 |
| `video:wan21-nsfw` | 55.0 |
