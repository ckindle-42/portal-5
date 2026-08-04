---
id: unit-comfyui-c10
kind: mixed
title: "Section C10 \u2014 Output validation"
sources:
- type: code
  path: tests/comfyui/c10_output_validation.py
  commit: 441fd2a1
last_generated_commit: 441fd2a1
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785798995.371858
updated_at: 1785798995.371858
---

This is the ComfyUI acceptance section c10. Section C10 — Output validation

## Why

It validates the generated outputs are real files with expected properties, not empty or corrupt artifacts — the check that a render that produced nothing would fail.

## Interfaces

The section drives the ComfyUI stack (direct API and/or the MCP bridge) and
records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live ComfyUI stack — its failures mean
the stack or the model configuration is broken, not the test.
