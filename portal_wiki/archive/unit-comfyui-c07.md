---
id: unit-comfyui-c07
kind: mixed
title: "Section C7 \u2014 Image generation: parameter sweep"
sources:
- type: code
  path: tests/comfyui/c07_param_sweep.py
  commit: 441fd2a1
last_generated_commit: 441fd2a1
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785798984.686089
updated_at: 1785798984.686089
---

This is the ComfyUI acceptance section c07. Section C7 — Image generation: parameter sweep

## Why

It proves the generation parameters (steps, cfg, dimensions) are honoured — a render that ignores a requested resolution or step count is silently wrong even if an image comes out.

## Interfaces

The section drives the ComfyUI stack (direct API and/or the MCP bridge) and
records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live ComfyUI stack — its failures mean
the stack or the model configuration is broken, not the test.
