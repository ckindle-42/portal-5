---
id: unit-surface-comfyui-tests
kind: mixed
title: "ComfyUI test suite \u2014 staged image/video stack verification"
sources:
- type: code
  path: tests/comfyui/*.py
last_generated_commit: 22007054d6cba73357ea3c5d7d7c97f5c252d7dc
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785886600.0
updated_at: 1785886600.0
---

The ComfyUI suite verifies the image and video stack as a staged progression,
not flat calls. Stages run preflight, image generation across FLUX and SDXL,
video, an E2E pipeline round-trip, and output validation. Every section
shares one harness contract, so a section body is assertions against helpers,
not its own plumbing.

## Why

ComfyUI failures on Apple Silicon are ambiguous: a render killed by
unified-memory pressure looks identical to a model misconfiguration, and a
leftover queue silently blocks every generation section. The runner enforces
the canonical C0 to C11 order with C0 always prepended, so prereqs, direct
API, MCP bridge health, and discovery are proven before the first render and
a failing section is evidence about its own stage. Separate FLUX dev, SDXL,
and LoRA-sweep sections keep family regressions from hiding behind faster
baselines.

## Interfaces

`_mcp` drives an MCP tool call and records the outcome via `record`; `_chat`
posts a non-streaming pipeline completion; `_comfyui_get` and `_comfyui_post`
hit the direct API; `_clear_comfyui_queue`, `_wait_for_comfyui_idle`, and
`_wait_for_comfyui_queue` keep the stack in a known state.
`_free_memory_for_comfyui` evicts Ollama models from unified memory, and
`_comfyui_watchdog` covers long renders. `ALL_ORDER` pins the runner's order,
`cli.py` parses the C-identifier selection, and `_write_results` emits the
run summary.

## Gotchas

`_parse_sections` prepends C0 unless prereqs are explicitly skipped, and an
unknown identifier exits loudly rather than running nothing. Failures
indicate the live stack or model configuration, not the test. The
unified-memory eviction contract stays in `unit-comfyui-common`, which
remains live.
