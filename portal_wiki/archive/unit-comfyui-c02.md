---
id: unit-comfyui-c02
kind: mixed
title: "Section C2 \u2014 MCP bridge health (comfyui_mcp, video_mcp)"
sources:
- type: code
  path: tests/comfyui/c02_mcp_health.py
  commit: 441fd2a1
last_generated_commit: 441fd2a1
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785798974.063594
updated_at: 1785798974.063594
---

This is the ComfyUI acceptance section c02. Section C2 — MCP bridge health (comfyui_mcp, video_mcp)

## Why

It verifies the MCP bridges (comfyui_mcp and video_mcp) answer their health endpoints, so a generation request routed through the MCP layer reaches a healthy bridge rather than failing inside it.

## Interfaces

The section drives the ComfyUI stack (direct API and/or the MCP bridge) and
records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live ComfyUI stack — its failures mean
the stack or the model configuration is broken, not the test.
