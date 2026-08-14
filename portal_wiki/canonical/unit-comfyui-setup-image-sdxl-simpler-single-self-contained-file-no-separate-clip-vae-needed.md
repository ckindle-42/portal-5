---
id: unit-comfyui-setup-image-sdxl-simpler-single-self-contained-file-no-separate-clip-vae-needed
kind: what
title: "COMFYUI_SETUP \u2014 Image: sdxl (simpler, single self-contained file, no\
  \ separate CLIP/VAE needed)"
sources:
- type: code
  path: portal/modules/media/tools/comfyui_mcp.py
- type: code
  path: portal/modules/media/tools/_admission.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5543349
updated_at: 1784946220.5543349
---

SDXL is the simpler backend because its checkpoint is self-contained. The
`SDXL_WORKFLOW` graph uses a single `CheckpointLoaderSimple` and draws the text
encoder from output slot 1 and the VAE from output slot 2 of that one file — no
separate `DualCLIPLoader` or `VAELoader` nodes, unlike the FLUX split-loader
graph. It is selected with `IMAGE_BACKEND=sdxl` and samples at 25 steps with a
CFG of 7.5 by default. The admission map mirrors that simplicity: the
`comfyui:sdxl` entry in `MEDIA_MODEL_MEMORY_GB` is a small single-file budget,
far below the multi-file FLUX estimate.

## Why

A self-contained checkpoint is operationally simpler on MPS because it needs no
assembly of separately downloaded encoders and costs less memory to load. That
is why the workflow exists as a minimal seven-node graph and why admission treats
it as the cheapest image backend — a deliberate contrast with the split-loader
complexity FLUX requires.
