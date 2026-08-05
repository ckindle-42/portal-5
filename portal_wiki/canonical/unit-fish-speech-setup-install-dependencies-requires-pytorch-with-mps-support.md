---
id: unit-fish-speech-setup-install-dependencies-requires-pytorch-with-mps-support
kind: what
title: "Install dependencies \u2014 torch with MPS support"
sources:
- type: code
  path: Dockerfile.mcp
- type: code
  path: portal/modules/media/tools/utils.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.538014
updated_at: 1784946220.538014
---

The speech containers do not need a host pip install because their Python
dependencies are baked into the images. `Dockerfile.mcp` installs `torch` and
`torchaudio` alongside `kokoro-onnx` and `soundfile`, and that same image serves
the TTS, music and document generation containers. Runtime device selection is
handled by `get_torch_device` in the shared media utilities, which returns `mps`
on Apple Silicon, `cuda` when a GPU is visible and `cpu` otherwise; the Fish
Speech loaders forward that value into `load_from_checkpoint`. There is no
separate `requirements.txt` step in the portal build, and `torchvision` is not
listed there.

## Why

Baking torch into the shared MCP image instead of telling operators to install it
by hand keeps every container reproducible and sidesteps the MPS wheel problems
that a manual macOS install tends to cause. The device helper centralises
selection so Fish Speech and music generation agree on what acceleration is
available instead of each probing independently.
