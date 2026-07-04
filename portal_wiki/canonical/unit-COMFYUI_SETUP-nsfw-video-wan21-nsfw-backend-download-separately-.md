---
id: unit-COMFYUI_SETUP-nsfw-video-wan21-nsfw-backend-download-separately-
kind: why
title: "COMFYUI_SETUP \u2014 NSFW video (wan21-nsfw backend) \u2014 download separately,\
  \ not via launch.sh:"
sources:
- type: design
  path: docs/COMFYUI_SETUP.md
  section: "NSFW video (wan21-nsfw backend) \u2014 download separately, not via launch.sh:"
last_generated_commit: ''
confidence: high
tags:
- docs
- COMFYUI_SETUP
created_at: 1783195000.829956
updated_at: 1783195000.829956
---

hf download NSFW-API/NSFW_Wan_14b nsfw_wan_14b_e15.safetensors \
    --local-dir ~/ComfyUI/models/diffusion_models/
hf download zootkitty/nsfw_wan_umt5-xxl_bf16_fixed nsfw_wan_umt5-xxl_bf16_fixed.safetensors \
    --local-dir ~/ComfyUI/models/text_encoders/
hf download ratoenien/wan_2.1_vae wan_2.1_vae.safetensors \
    --local-dir ~/ComfyUI/models/vae/
