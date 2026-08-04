---
id: unit-comfyui-setup-quick-install-apple-silicon
kind: what
title: "COMFYUI_SETUP \u2014 Quick Install (Apple Silicon)"
sources:
- type: code
  path: scripts/lib/services.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.553226
updated_at: 1784946220.553226
---

`./launch.sh install-comfyui` installs the engine on Apple Silicon. The handler
exits early on any non-arm64 machine with a pointer to the Docker profile. On a
supported host it clones the ComfyUI repository into `~/ComfyUI`, creates an
isolated virtual environment, installs the project requirements plus the PyTorch
family, and provisions the standard model directories. It writes the launch
script, installs the VideoHelperSuite custom node for video output, and registers
a launchd agent that starts on login and restarts on exit, with logs redirected
under the home portal directory.

## Why

A dedicated installer exists because ComfyUI sits outside the Docker lifecycle,
and on Apple Silicon the entire point is running on the Metal device the
container boundary would blunt. Bundling clone, venv, torch install, and agent
registration into one command keeps the optional add-on reproducible instead of
documented-as-mandatory.
