---
id: unit-comfyui-setup-quick-install-apple-silicon
kind: what
title: "COMFYUI_SETUP \u2014 Quick Install (Apple Silicon)"
sources:
- type: doc
  path: docs/COMFYUI_SETUP.md
  commit: 05e42ec2
  section: Quick Install (Apple Silicon)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.553226
updated_at: 1784946220.553226
---

```bash
./launch.sh install-comfyui
```

This clones ComfyUI to `~/ComfyUI`, installs PyTorch with MPS support,
and registers it as a launchd service that auto-starts on login.
