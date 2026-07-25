---
id: unit-comfyui-setup-video-wan21-nsfw-currently-configured-video-backend-in-env
kind: what
title: "COMFYUI_SETUP \u2014 Video: wan21-nsfw (currently configured `VIDEO_BACKEND`\
  \ in `.env`)"
sources:
- type: doc
  path: docs/COMFYUI_SETUP.md
  commit: 05e42ec2
  section: 'Video: wan21-nsfw (currently configured `VIDEO_BACKEND` in `.env`)'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.554705
updated_at: 1784946220.554705
---

```bash
hf download NSFW-API/NSFW_Wan_14b nsfw_wan_14b_e15.safetensors \
    --local-dir ~/ComfyUI/models/diffusion_models/
hf download zootkitty/nsfw_wan_umt5-xxl_bf16_fixed nsfw_wan_umt5-xxl_bf16_fixed.safetensors \
    --local-dir ~/ComfyUI/models/text_encoders/
hf download ratoenien/wan_2.1_vae wan_2.1_vae.safetensors \
    --local-dir ~/ComfyUI/models/vae/
