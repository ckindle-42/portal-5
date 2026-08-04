---
id: unit-comfyui-setup-cinematic-quality-t2v-a14b-slower
kind: what
title: "COMFYUI_SETUP \u2014 Cinematic quality (T2V-A14B, slower)"
sources:
- type: code
  path: portal/modules/media/tools/video_mcp.py
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.557782
updated_at: 1784946220.557782
---

The cinematic-quality video preset is not available because Portal 5 operates
image generation only. The Wan 2.2 T2V-A14B backend still exists as code: the
`_WAN22_T2V_A14B_WORKFLOW` graph in `video_mcp.py` chains a high-noise and a
low-noise `UNETLoader` through two staged `KSamplerAdvanced` nodes that split the
denoising steps in half, matching ComfyUI's reference two-expert MoE layout.
Every published fp8-scaled checkpoint for it crashes on Apple Silicon MPS at
dequantization, and the `mcp-video` container is profile-gated in the compose
file. No quality T2V preset is reachable anywhere; the workflow is retained as an
archival implementation.

## Why

The graph mirrors ComfyUI's official Wan 2.2 template because the high-noise and
low-noise experts ship as separate checkpoints with no merged single file; a
single UNETLoader assumption would silently drop half the model. The workflow is
kept alongside the shelving decision so that resuming video later — after MPS fp8
support improves — starts from code that already reflects the real layout rather
than a guessed graph.
