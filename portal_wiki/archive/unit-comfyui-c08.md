---
id: unit-comfyui-c08
kind: mixed
title: "Section C8 \u2014 Video generation: Wan2.2 T2V via MCP"
sources:
- type: code
  path: tests/comfyui/c08_video_wan22.py
  commit: 441fd2a1
last_generated_commit: 441fd2a1
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785798988.250659
updated_at: 1785798988.250659
---

This is the ComfyUI acceptance section c08. Section C8 — Video generation: Wan2.2 T2V via MCP

## Why

It proves the video path renders through the MCP bridge. Video is the longest and heaviest generation, so its section is where a memory or queue-management regression shows first.

## Interfaces

The section drives the ComfyUI stack (direct API and/or the MCP bridge) and
records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live ComfyUI stack — its failures mean
the stack or the model configuration is broken, not the test.
