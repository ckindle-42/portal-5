---
id: unit-comfyui-c06
kind: mixed
title: "ComfyUI acceptance C6 \u2014 SDXL variants"
sources:
- type: code
  path: tests/comfyui/c06_sdxl.py
  commit: 441fd2a1
last_generated_commit: 441fd2a1
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785799029.749126
updated_at: 1785799029.749126
---

This is the ComfyUI acceptance section C06. Image generation: SDXL
variants.

## Why

The SDXL family is the second model family the fleet exposes, with its own
checkpoint and parameter conventions. Proving the SDXL variants render is
what covers that family's path independently of the FLUX path, so a
regression that breaks SDXL but not FLUX is caught here rather than hiding
behind the FLUX sections passing.

## Interfaces

The section drives the ComfyUI stack (direct API and/or the MCP bridge) and
records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live ComfyUI stack — its failures mean
the stack or the model configuration is broken, not the test.
