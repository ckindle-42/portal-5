---
id: unit-comfyui-c03
kind: mixed
title: "Section C3 \u2014 Model discovery via MCP"
sources:
- type: code
  path: tests/comfyui/c03_model_discovery.py
  commit: 441fd2a1
last_generated_commit: 441fd2a1
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785798977.583313
updated_at: 1785798977.583313
---

This is the ComfyUI acceptance section c03. Section C3 — Model discovery via MCP

## Why

It confirms the MCP bridge can enumerate the models ComfyUI actually has loaded. Discovery is the precondition for generation sections — a section that asks for a model the bridge cannot see would fail for the wrong reason.

## Interfaces

The section drives the ComfyUI stack (direct API and/or the MCP bridge) and
records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live ComfyUI stack — its failures mean
the stack or the model configuration is broken, not the test.
