---
id: unit-known-limitations-comfyui-runs-outside-docker
kind: what
title: "KNOWN_LIMITATIONS \u2014 ComfyUI Runs Outside Docker"
sources:
- type: code
  path: scripts/lib/services.sh
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.663147
updated_at: 1784946220.663147
---

- **Description**: ComfyUI runs on the host (not in Docker) to access MPS directly. `_launch_install_comfyui` in `scripts/lib/services.sh` installs it natively on Apple Silicon via git+pip; on non-Apple-Silicon it exits with pointers to Docker (via the compose `docker-comfyui` profile) or a manual install. Native host execution is required for supported image-generation performance; video operation is shelved.
- **Impact**: Manual setup is required outside `./launch.sh up`. On a fresh machine, ComfyUI must be installed separately with `./launch.sh install-comfyui`; the media MCPs reach it over HTTP rather than through the compose stack.
- **Mitigation**: `./launch.sh install-comfyui` handles setup on supported platforms. See `docs/COMFYUI_SETUP.md`.

## Why

ComfyUI on Apple Silicon needs direct access to the Metal/MPS device, which a container boundary would blunt or break, so the supported path runs it on the host with its own launchd agent. That keeps inference performance but moves ComfyUI out of the one-command compose lifecycle — hence the dedicated install command and setup doc that document the divergence.
