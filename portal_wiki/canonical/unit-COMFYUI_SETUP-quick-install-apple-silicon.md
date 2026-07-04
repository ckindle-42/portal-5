---
id: unit-COMFYUI_SETUP-quick-install-apple-silicon
kind: why
title: "COMFYUI_SETUP \u2014 Quick Install (Apple Silicon)"
sources:
- type: design
  path: docs/COMFYUI_SETUP.md
  section: Quick Install (Apple Silicon)
last_generated_commit: ''
confidence: high
tags:
- docs
- COMFYUI_SETUP
created_at: 1783195000.829488
updated_at: 1783195000.829488
---


```bash
./launch.sh install-comfyui
```

This clones ComfyUI to `~/ComfyUI`, installs PyTorch with MPS support,
and registers it as a launchd service that auto-starts on login.
