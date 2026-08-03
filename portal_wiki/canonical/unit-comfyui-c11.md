---
id: unit-comfyui-c11
kind: mixed
title: "Section C11 \u2014 All LoRAs x FLUX schnell coverage"
sources:
- type: code
  path: tests/comfyui/c11_lora_coverage.py
  commit: 441fd2a1
last_generated_commit: 441fd2a1
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785798998.9102561
updated_at: 1785798998.9102561
---

This is the ComfyUI acceptance section c11. Section C11 — All LoRAs x FLUX schnell coverage

## Why

It sweeps every LoRA against FLUX schnell, closing the coverage gap where an earlier section tested only the first regular and first NSFW LoRA. A LoRA that breaks the pipeline or fails to apply is found here, across the whole arsenal.

## Interfaces

The section drives the ComfyUI stack (direct API and/or the MCP bridge) and
records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live ComfyUI stack — its failures mean
the stack or the model configuration is broken, not the test.
