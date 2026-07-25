---
id: unit-comfyui-setup-image-sdxl-simpler-single-self-contained-file-no-separate-clip-vae-needed
kind: what
title: "COMFYUI_SETUP \u2014 Image: sdxl (simpler, single self-contained file, no\
  \ separate CLIP/VAE needed)"
sources:
- type: doc
  path: docs/COMFYUI_SETUP.md
  commit: 05e42ec2
  section: 'Image: sdxl (simpler, single self-contained file, no separate CLIP/VAE
    needed)'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5543349
updated_at: 1784946220.5543349
---

```bash
hf download stabilityai/stable-diffusion-xl-base-1.0 sd_xl_base_1.0.safetensors \
    --local-dir ~/ComfyUI/models/checkpoints/
```
Set `IMAGE_BACKEND=sdxl` in `.env`.
