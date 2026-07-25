---
id: unit-comfyui-setup-ti2v-5b-fast-image-to-video-single-file-comfyui-native-repackaging
kind: what
title: "COMFYUI_SETUP \u2014 TI2V-5B (fast, image-to-video): single-file ComfyUI-native\
  \ repackaging"
sources:
- type: doc
  path: docs/COMFYUI_SETUP.md
  commit: 05e42ec2
  section: 'TI2V-5B (fast, image-to-video): single-file ComfyUI-native repackaging'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.556318
updated_at: 1784946220.556318
---

hf download Comfy-Org/Wan_2.2_ComfyUI_Repackaged \
    split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors \
    split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors \
    split_files/vae/wan2.2_vae.safetensors \
    --local-dir ~/ComfyUI/models
```

T2V-A14B's weight source is not yet pinned down (see `WAN22_T2V_UNET` comment in
`video_mcp.py` — "requires separate download, not yet in pull-wan22").
