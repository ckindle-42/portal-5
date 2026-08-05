---
id: unit-comfyui-setup-video-wan21-nsfw-currently-configured-video-backend-in-env
kind: what
title: "COMFYUI_SETUP \u2014 Video: wan21-nsfw (currently configured `VIDEO_BACKEND`\
  \ in `.env`)"
sources:
- type: code
  path: portal/modules/media/tools/video_mcp.py
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.554705
updated_at: 1784946220.554705
---

The unit's title is stale: the currently configured default is not wan21-nsfw.
Both the compose environment and `.env.example` set `VIDEO_BACKEND` to wan22.
The wan21-nsfw backend is legacy code in `video_mcp.py` — a dedicated NSFW
fine-tune checkpoint with a matched text encoder and VAE, driven by a CLIPLoader
typed for the Wan architecture and a CFG-guider sampler stack — and its memory
admission estimate is set well above its static weight because a measured peak
consumed nearly the entire unified pool. Its weights are not fetched by any
current command, and enabling it is outside the supported image-only install.

## Why

The default drifted from the documentation while the code stayed put, and the
unit's job is to make the actual state — wan22 as the compose default, wan21-nsfw
as unoperated legacy — the discoverable truth. The admission figure also encodes
a hard-won incident: the measured peak of this backend wildly exceeded its disk
size.
