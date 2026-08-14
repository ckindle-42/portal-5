---
id: unit-comfyui-setup-flux-images-are-pure-static-tv-noise
kind: what
title: "COMFYUI_SETUP \u2014 FLUX images are pure static / TV noise"
sources:
- type: code
  path: scripts/lib/services.sh
- type: code
  path: portal/modules/media/tools/comfyui_mcp.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5624719
updated_at: 1784946220.5624719
---

`--force-fp16` is nowhere in the ComfyUI launch path. The install function
`_launch_install_comfyui` writes `start.sh` and the launchd plist with only the
listen address and port arguments, and the MCP's ETA estimator documents its
Apple Silicon timing assumption as running without fp16. The FLUX graph itself
pins the `KSampler` cfg to 1.0 and routes guidance through the `FluxGuidance`
node, because CFG-style extrapolation on a flow-matching model with a real CFG
scale produces exactly the static output users report. If FLUX output looks like
TV noise while SDXL is clean, inspect the running process flags; a launch script
carrying `--force-fp16` is the classic cause and must be edited out.

## Why

FLUX is a diffusion transformer whose attention math accumulates float16
precision error across sampling steps, so forcing fp16 on MPS degrades the output
to noise; SDXL's convolutional U-Net tolerates the same precision loss. The
launch scripts therefore must never add the flag, and the workflow keeps CFG at
1.0 with separate guidance scaling for the same numerical-sensitivity reason.
