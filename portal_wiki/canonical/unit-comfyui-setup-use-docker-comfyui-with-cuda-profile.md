---
id: unit-comfyui-setup-use-docker-comfyui-with-cuda-profile
kind: what
title: "COMFYUI_SETUP \u2014 Use Docker ComfyUI with CUDA profile"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5609212
updated_at: 1784946220.5609212
---

The Docker path for non-Apple-Silicon hosts is the `docker-comfyui` profile, but
the documented `./launch.sh up --profile docker-comfyui` form is inaccurate: the
launch script's up command forwards only auto-detected channel profiles and does
not pass a profile argument through. The correct activation is a direct compose
invocation from the deploy directory with the profile flag. The service image is
the CPU-tagged ai-dock build on the amd64 platform, and NVIDIA acceleration is
selected by setting `CF_TORCH_DEVICE` to cuda rather than by any GPU reservation
in the compose file.

## Why

The unit corrects a command that cannot work because profile activation is a
compose-level flag and launch.sh deliberately hides profile mechanics behind its
own interface. Recording the real invocation prevents an operator on a Linux
NVIDIA host from concluding the Docker path is broken when the wrapper simply
does not forward the flag.
