---
id: unit-comfyui-c00
kind: mixed
title: "Section C0 \u2014 Prerequisites (memory, deps, ComfyUI process)"
sources:
- type: code
  path: tests/comfyui/c00_prereqs.py
  commit: 441fd2a1
last_generated_commit: 441fd2a1
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785798966.950432
updated_at: 1785798966.950432
---

This is the ComfyUI acceptance section c00. Section C0 — Prerequisites (memory, deps, ComfyUI process)

## Why

It verifies the preconditions every later section assumes: unified memory is free enough, the required dependencies are present, and the ComfyUI process is actually running. Running a generation test against a stack that was never confirmed up would produce a failure that looks like the model when it is actually the prerequisites.

## Interfaces

The section drives the ComfyUI stack (direct API and/or the MCP bridge) and
records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live ComfyUI stack — its failures mean
the stack or the model configuration is broken, not the test.
