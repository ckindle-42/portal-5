---
id: unit-comfyui-setup-image-flux-schnell-default
kind: what
title: "COMFYUI_SETUP \u2014 Image: flux-schnell (default)"
sources:
- type: code
  path: portal/modules/media/tools/comfyui_mcp.py
- type: code
  path: deploy/portal-5/docker-compose.yml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.553955
updated_at: 1784946220.553955
---

Flux is the default image backend. The MCP resolves `IMAGE_BACKEND` to the
checkpoint via `_MODEL_CKPT_MAP`, and the compose service's environment block
carries matching defaults: `FLUX_CKPT_FILE` for the UNet, `FLUX_CLIP_L_FILE` for
the CLIP-L encoder, `FLUX_CLIP_T5_FILE` for the T5 encoder, and `FLUX_VAE_FILE`
for the autoencoder. The split-loader workflow (`FLUX_WORKFLOW`) loads CLIP and
VAE as separate nodes because the official schnell checkpoint carries no embedded
text encoder or VAE. The T5 filename must point at the single-file ComfyUI-native
repackaging; pointing at one shard of the raw diffusers sharded T5 silently loads
half the weights and fails prompt validation with a "Value not in list" error
from `DualCLIPLoader`.

## Why

The flux checkpoint ships without text encoders, so the split-loader graph is the
only way to condition prompts, and each component file is a separately tracked
env default to keep the workflow honest about what is actually installed. The
single-file T5 requirement exists because `DualCLIPLoader` performs a plain
single-file state-dict load, so a lone shard of a sharded encoder is silently
wrong.
