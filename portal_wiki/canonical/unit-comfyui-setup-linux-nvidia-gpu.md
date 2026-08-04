---
id: unit-comfyui-setup-linux-nvidia-gpu
kind: what
title: "COMFYUI_SETUP \u2014 Linux (NVIDIA GPU)"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.560558
updated_at: 1784946220.560558
---

On Linux the Docker route is the `docker-comfyui` profile. The compose file
defines a `comfyui` service from the ai-dock image pinned to the CPU tag with an
explicit `linux/amd64` platform, loopback port 8188, and a health check that
probes `system_stats`. Torch device selection is driven by the
`CF_TORCH_DEVICE` environment variable, which defaults to cpu; setting it to cuda
in `.env` moves compute onto an NVIDIA GPU. The compose definition itself
reserves no GPU device — the image tag is the CPU variant, so CUDA support is
inherited from the ai-dock image rather than declared in the compose file.

## Why

ComfyUI runs host-native on Apple Silicon to reach MPS directly, so the Docker
image is the fallback only for platforms that cannot run a host process — hence
the amd64 CPU default and the device knob rather than a GPU reservation. Keeping
CUDA opt-in via an env var preserves a working CPU container everywhere while
letting NVIDIA hosts accelerate without a second image.
