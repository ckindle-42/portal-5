---
id: unit-comfyui-setup-portal-5-comfyui-setup-guide
kind: what
title: "COMFYUI_SETUP \u2014 Portal 5 \u2014 ComfyUI Setup Guide"
sources:
- type: code
  path: scripts/lib/services.sh
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: 75c5054f791636f367b62a1776bcc9f631794766
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.552777
updated_at: 1784946220.552777
---

This is the top-level orientation for the ComfyUI integration. ComfyUI is the
image-generation engine and runs natively on the host rather than in a container,
so the MPS accelerator is reachable directly. The `mcp-comfyui` bridge container
is enabled by default in the compose file and reaches the engine through the
`COMFYUI_URL` address, while the browser-facing links use the public URL. The
video service that once shared this lane is shelved and profile-gated, so the
guide's supported scope is image generation: install via launch.sh, pull models
per family, generate through the MCP tools.

## Why

The native-vs-container split is the load-bearing decision of the whole setup:
Metal access requires the engine to be a host process, which in turn is why
installation, model pulling, and lifecycle management all sit in launch.sh
scripts instead of compose profiles, and why the compose stack only ever talks to
ComfyUI over HTTP.
