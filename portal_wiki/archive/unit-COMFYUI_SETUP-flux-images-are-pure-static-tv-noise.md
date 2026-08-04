---
id: unit-COMFYUI_SETUP-flux-images-are-pure-static-tv-noise
kind: why
title: "COMFYUI_SETUP \u2014 FLUX images are pure static / TV noise"
sources:
- type: design
  path: docs/COMFYUI_SETUP.md
  section: FLUX images are pure static / TV noise
last_generated_commit: ''
confidence: high
tags:
- docs
- COMFYUI_SETUP
created_at: 1783195000.832096
updated_at: 1783195000.832096
---


**Do not use `--force-fp16`** with FLUX on Apple Silicon MPS. FLUX's transformer
attention layers are numerically sensitive — float16 precision errors compound over
sampling steps until the output is indistinguishable from noise. SDXL tolerates fp16
fine because its U-Net architecture is more forgiving; FLUX does not.

`~/ComfyUI/start.sh` and the LaunchAgent plist must NOT include `--force-fp16`.
ComfyUI runs FLUX in bfloat16/float32 by default on MPS, which is correct.

If you see static with FLUX but clean images from SDXL, check:
```bash
ps aux | grep "main.py" | grep -v grep   # should NOT show --force-fp16
```

If it shows `--force-fp16`, edit `~/ComfyUI/start.sh` and
`~/Library/LaunchAgents/com.portal5.comfyui.plist` to remove it, then restart
ComfyUI.
