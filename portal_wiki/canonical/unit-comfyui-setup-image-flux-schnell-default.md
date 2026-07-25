---
id: unit-comfyui-setup-image-flux-schnell-default
kind: what
title: "COMFYUI_SETUP \u2014 Image: flux-schnell (default)"
sources:
- type: doc
  path: docs/COMFYUI_SETUP.md
  commit: 05e42ec2
  section: 'Image: flux-schnell (default)'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.553955
updated_at: 1784946220.553955
---

```bash
hf download black-forest-labs/FLUX.1-schnell flux1-schnell.safetensors \
    --local-dir ~/ComfyUI/models/checkpoints/
hf download black-forest-labs/FLUX.1-schnell ae.safetensors \
    --local-dir ~/ComfyUI/models/vae/
hf download comfyanonymous/flux_text_encoders clip_l.safetensors \
    --local-dir ~/ComfyUI/models/clip/
hf download comfyanonymous/flux_text_encoders t5xxl_fp8_e4m3fn.safetensors \
    --local-dir ~/ComfyUI/models/clip/
```

Set in `.env` (or leave at these defaults — they now match `comfyui_mcp.py`):
```
IMAGE_BACKEND=flux
FLUX_CKPT_FILE=flux1-schnell.safetensors
FLUX_CLIP_L_FILE=clip_l.safetensors
FLUX_CLIP_T5_FILE=t5xxl_fp8_e4m3fn.safetensors
FLUX_VAE_FILE=ae.safetensors
```

**Do not** point `FLUX_CLIP_T5_FILE` at the raw diffusers repo's sharded
`text_encoder_2/model-00001-of-00002.safetensors` — `DualCLIPLoader` does a plain
single-file state-dict load, so a lone shard silently loads only half the T5 weights and
fails prompt validation with `Value not in list: clip_name2`. Use the single-file
ComfyUI-native repackaging (`comfyanonymous/flux_text_encoders`) above instead.

`flux-uncensored` (`Flux_v8-NSFW.safetensors` in `comfyui_mcp.py`'s `_MODEL_CKPT_MAP`) has
no currently-known working source — the old script's repo
(`enhanceaiteam/Flux-Uncensored-V2`) returns 404. Use `sdxl` or plain `flux` instead until
a source is found.
