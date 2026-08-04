---
id: unit-comfyui-c04
kind: mixed
title: "Section C4 \u2014 Image generation: FLUX schnell"
sources:
- type: code
  path: tests/comfyui/c04_flux_schnell.py
  commit: 441fd2a1
last_generated_commit: 441fd2a1
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785798981.099617
updated_at: 1785798981.099617
---

This is the ComfyUI acceptance section c04. Section C4 — Image generation: FLUX schnell

## Why

It proves the fastest FLUX variant actually renders an image end to end, establishing the baseline generation path that the dev, SDXL, and LoRA sections extend.

## Interfaces

The section drives the ComfyUI stack (direct API and/or the MCP bridge) and
records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live ComfyUI stack — its failures mean
the stack or the model configuration is broken, not the test.
