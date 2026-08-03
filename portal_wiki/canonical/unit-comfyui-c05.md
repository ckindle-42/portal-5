---
id: unit-comfyui-c05
kind: mixed
title: "ComfyUI acceptance C5 \u2014 FLUX dev generation"
sources:
- type: code
  path: tests/comfyui/c05_flux_dev.py
  commit: 441fd2a1
last_generated_commit: 441fd2a1
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785799026.2191942
updated_at: 1785799026.2191942
---

This is the ComfyUI acceptance section C05. Image generation: FLUX dev.

## Why

FLUX dev is the higher-quality variant and the model the LoRA coverage
section depends on, so proving it renders end to end is the precondition for
every later section that applies a LoRA to it. A dev failure that surfaced
only as a downstream LoRA failure would be misdiagnosed, which is why dev
has its own section before the sweep.

## Interfaces

The section drives the ComfyUI stack (direct API and/or the MCP bridge) and
records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live ComfyUI stack — its failures mean
the stack or the model configuration is broken, not the test.
