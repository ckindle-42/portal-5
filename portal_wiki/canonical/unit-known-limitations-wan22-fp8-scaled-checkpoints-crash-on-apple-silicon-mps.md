---
id: unit-known-limitations-wan22-fp8-scaled-checkpoints-crash-on-apple-silicon-mps
kind: what
title: "KNOWN_LIMITATIONS \u2014 Wan 2.2 fp8_scaled Checkpoints Crash on Apple Silicon\
  \ MPS (Video Generation Shelved)"
sources:
- type: code
  path: portal/modules/media/tools/video_mcp.py
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: scripts/lib/services.sh
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1785292615.0
updated_at: 1785292615.0
---

- **Description**: Every Wan 2.2 ComfyUI checkpoint published as `*_fp8_scaled.safetensors` (Comfy-Org/Wan_2.2_ComfyUI_Repackaged) crashes at inference time on this host's Apple Silicon MPS stack with an undefined fp8 dtype error during the dequantization of the fp8 diffusion weights. Confirmed live against the T2V-A14B high/low-noise pair and the S2V-14B checkpoint, each with all three `UNETLoader` `weight_dtype` options, failing the same way every time during model load. `wan2.2_ti2v_5B_fp16.safetensors` (TI2V-5B) is unaffected because it is full fp16, not fp8-quantized — it generated successfully end to end.
- **Impact**: T2V-A14B and S2V-14B are unusable on this hardware via their `_fp8_scaled` checkpoints. The only working alternative is full fp16/bf16, roughly 90GB combined and against the project's usual quantized-only model policy — a genuine hardware blocker rather than a quality tradeoff. `video_mcp.py`'s `_WAN22_T2V_A14B_WORKFLOW` was also independently corrected to the real two-expert MoE graph (two `UNETLoader` + two chained `KSamplerAdvanced`), matching ComfyUI's official reference workflow, in the same session and independent of the fp8 finding.
- **Decision (2026-07-29)**: Video generation is shelved for this project — Portal 5 operates ComfyUI **image** generation (via `mcp-comfyui`), not video. The `mcp-video` container is profile-gated and not part of the default `./launch.sh up` set; `deploy/portal-5/docker-compose.yml` documents that image and video were split into separate profiles so gating video does not take images down. The video workflow code is left in place — designed, not deleted — in case MPS fp8 support improves later, but nothing video-related should be treated as in operation.
- **Mitigation**: None pursued. If video generation is revisited, first check whether a newer PyTorch/comfy_kitchen release fixes MPS fp8 support, then fall back to the fp16/bf16 downloads.

## Why

The fp8_scaled checkpoint family is the standard published form of Wan 2.2, and it fails on MPS at the dequantization step — a PyTorch/comfy_kitchen platform gap, not a workflow bug. Shelving video rather than carrying a broken, unquantized 90GB path keeps the fleet policy consistent, while splitting the compose profiles preserves image generation, which was never the problem. The corrected workflow and the decision are recorded so the shelving is reversible when MPS support lands.
