---
id: unit-known-limitations-comfyui-runs-outside-docker
kind: what
title: "KNOWN_LIMITATIONS \u2014 ComfyUI Runs Outside Docker"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: ComfyUI Runs Outside Docker
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.663147
updated_at: 1784946220.663147
---

- **Description**: ComfyUI runs on the host (not in Docker) to access MPS/CUDA directly. Required for image/video generation performance.
- **Impact**: Manual setup required outside `./launch.sh up`. On a fresh machine, ComfyUI must be installed separately.
- **Mitigation**: `./launch.sh install-comfyui` handles setup on supported platforms. See `docs/COMFYUI_SETUP.md`.
