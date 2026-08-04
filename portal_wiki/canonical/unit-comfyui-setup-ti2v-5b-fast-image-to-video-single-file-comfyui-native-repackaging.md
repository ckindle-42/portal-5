---
id: unit-comfyui-setup-ti2v-5b-fast-image-to-video-single-file-comfyui-native-repackaging
kind: what
title: "COMFYUI_SETUP \u2014 TI2V-5B (fast, image-to-video): single-file ComfyUI-native\
  \ repackaging"
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
created_at: 1784946220.556318
updated_at: 1784946220.556318
---

The TI2V-5B lane is shelved despite being verified. Its single-file checkpoint is
`wan2.2_ti2v_5B_fp16.safetensors` — the compose default for `WAN22_TI2V_MODEL` —
and the workflow in `video_mcp.py` consumes a start-frame image through
`Wan22ImageToVideoLatent`, producing video at a default resolution and frame
count. Full fp16 is why it avoided the fp8 dequantization crash that disabled the
rest of the family. The project nevertheless decided not to expose one working
video variant while the others fail, so neither a tool nor a preset presents it.

## Why

Exposing a single verified lane among broken siblings would advertise video
operation the fleet does not actually run. Keeping the workflow and its env
defaults in the code preserves the proof it works and the exact download target,
so re-enabling later is a registration change rather than a reconstruction.
