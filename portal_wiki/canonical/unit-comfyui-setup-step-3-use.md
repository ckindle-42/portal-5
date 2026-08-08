---
id: unit-comfyui-setup-step-3-use
kind: what
title: "COMFYUI_SETUP \u2014 Step 3 \u2014 Use"
sources:
- type: code
  path: scripts/gen-image.py
- type: code
  path: portal/modules/media/tools/comfyui_mcp.py
last_generated_commit: 59839264613bae9f5c35a66902c8cc274654191d
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5570261
updated_at: 1784946220.5570261
---

Usage runs through the image MCP rather than the raw engine API. The
`gen-image.py` CLI posts a generation request to the bridge on the loopback port,
then polls status until the image is ready, and can send a push notification when
done. The underlying MCP exposes blocking generation, an asynchronous start plus
status lookup, a recent-images listing, and a workflow listing. The CLI ships
presets: the default FLUX run, a quality profile at higher resolution, a fast
profile with fewer steps, and a family of Qwen-Image presets for text rendering.

## Why

Exposing a poll-loop CLI on top of the async MCP tools gives a terminal operator
the same job tracking the chat interface gets from start-then-status, without
blocking for minutes on a single call. The preset table collapses the model,
step, and guidance decisions into named choices so iteration is repeatable.
