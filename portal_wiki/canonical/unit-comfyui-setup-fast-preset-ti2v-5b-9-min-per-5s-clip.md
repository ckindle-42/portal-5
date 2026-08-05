---
id: unit-comfyui-setup-fast-preset-ti2v-5b-9-min-per-5s-clip
kind: what
title: "COMFYUI_SETUP \u2014 Fast preset (TI2V-5B, ~9 min per 5s clip)"
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
created_at: 1784946220.557384
updated_at: 1784946220.557384
---

No fast TI2V preset is exposed. The image-to-video backend itself is real code:
`_WAN22_TI2V_5B_WORKFLOW` in `video_mcp.py` feeds a `LoadImage` start frame into
`Wan22ImageToVideoLatent` and samples it at a default resolution over 121 frames
(about five seconds at 24 fps), with the single-file fp16 checkpoint
`wan2.2_ti2v_5B_fp16.safetensors` configured as the compose default for
`WAN22_TI2V_MODEL`. It was verified working because full fp16 avoids the fp8
dequantization crash that kills the other Wan 2.2 variants. The project then
chose not to expose a lone partial video family, so `mcp-video` stays profile
gated and no preset exists in any CLI.

## Why

The TI2V variant survived because it is the only Wan 2.2 checkpoint shipped as
full fp16 rather than fp8-quantized, so it never hits the MPS dequantization
failure. Shelving it anyway, despite the proof it works, reflects a deliberate
scoping decision: advertising one working video lane alongside several broken
ones would mislead operators into expecting a service that is not operated.
