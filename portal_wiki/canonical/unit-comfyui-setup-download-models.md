---
id: unit-comfyui-setup-download-models
kind: what
title: "COMFYUI_SETUP \u2014 Download Models"
sources:
- type: doc
  path: docs/COMFYUI_SETUP.md
  commit: 05e42ec2
  section: Download Models
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.553596
updated_at: 1784946220.553596
---

Use `./launch.sh pull-qwen-image` to download the image-generation set verified on
Apple Silicon MPS: Qwen-Image-2512 plain FP8, Qwen-Image-Edit-2509 plain FP8,
the shared FP8-scaled text encoder and VAE, and the Lightning LoRA (about 48 GiB
total). The command installs files in ComfyUI's flat model layout and skips files
already present.

`./launch.sh download-comfyui-models` is a retired legacy alias because its old
monolithic downloader was deleted. Use the explicit family command above. Video
generation is shelved and is not part of the supported ComfyUI setup.
