---
id: unit-comfyui-c09
kind: mixed
title: "Section C9 \u2014 Pipeline round-trips (auto-video)"
sources:
- type: code
  path: tests/comfyui/c09_pipeline_roundtrip.py
  commit: 441fd2a1
last_generated_commit: 441fd2a1
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785798991.79806
updated_at: 1785798991.79806
---

This is the ComfyUI acceptance section c09. Section C9 — Pipeline round-trips (auto-video)

## Why

It proves the full pipeline round-trip: a persona request through the pipeline reaches the video workspace and returns a result, exercising the routing plus generation path rather than the API in isolation.

## Interfaces

The section drives the ComfyUI stack (direct API and/or the MCP bridge) and
records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live ComfyUI stack — its failures mean
the stack or the model configuration is broken, not the test.
