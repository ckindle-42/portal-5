---
id: unit-COMFYUI_SETUP-wan-2-2-family-v6-2-addition
kind: why
title: "COMFYUI_SETUP \u2014 Wan 2.2 Family (v6.2 addition)"
sources:
- type: design
  path: docs/COMFYUI_SETUP.md
  section: Wan 2.2 Family (v6.2 addition)
last_generated_commit: ''
confidence: high
tags:
- docs
- COMFYUI_SETUP
created_at: 1783195000.830217
updated_at: 1783195000.830217
---


Wan 2.2 is the MoE successor to Wan 2.1 (27B total / 14B active per step). Four variants are supported as parallel ComfyUI workflows. The Wan 2.1 NSFW pipeline is unchanged and remains the default for NSFW-tagged requests.

| Variant | Model ID | Size | Best for |
|---|---|---|---|
| `wan22-t2v-a14b` | `wan22-t2v-a14b` | 27B/14B-active | Cinematic-quality text-to-video |
| `wan22-ti2v-5b` | `wan22-ti2v-5b` | 5B | Fast single-GPU text/image-to-video (~9 min per 5s clip) |
| `wan22-animate-14b` | `wan22-animate-14b` | 14B | Character animation / replacement (**NEW capability**) |
| `wan22-s2v-14b` | `wan22-s2v-14b` | 14B | Speech-driven video generation (**NEW capability**) |

All four are Apache 2.0 licensed.
