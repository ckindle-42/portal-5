---
id: unit-comfyui-c01
kind: mixed
title: "Section C1 \u2014 ComfyUI direct API (system stats, object info, models)"
sources:
- type: code
  path: tests/comfyui/c01_direct_api.py
  commit: 441fd2a1
last_generated_commit: 441fd2a1
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785798970.477257
updated_at: 1785798970.477257
---

This is the ComfyUI acceptance section c01. Section C1 — ComfyUI direct API (system stats, object info, models)

## Why

It exercises the direct HTTP API independent of the MCP bridge, confirming the server answers its system stats, object info, and model endpoints. This establishes that the underlying service is healthy before any MCP-layer test that could mask a direct-API breakage.

## Interfaces

The section drives the ComfyUI stack (direct API and/or the MCP bridge) and
records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live ComfyUI stack — its failures mean
the stack or the model configuration is broken, not the test.
