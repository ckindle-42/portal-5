---
id: unit-comfyui-common
kind: mixed
title: "ComfyUI acceptance common \u2014 shared section infrastructure"
sources:
- type: code
  path: tests/comfyui/_common.py
  commit: 441fd2a1
last_generated_commit: 441fd2a1
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785798948.683946
updated_at: 1785798948.683946
---

`_common.py` is the shared infrastructure for the ComfyUI acceptance
sections: it re-exports the result-recording surface from `tests.lib`,
loads the environment, defines the service URLs and auth, and provides the
helpers the sections use — MCP tool calls, pipeline chat, direct ComfyUI
API calls, queue waiting, memory eviction, and the long-run watchdog.

## Why

The twelve sections need the same plumbing (talk to ComfyUI directly, talk
to the MCP bridge, talk to the pipeline, record results, free unified
memory) and duplicating it per section would be the drift this project
pays to avoid. The memory helpers exist because ComfyUI and Ollama share
Apple Silicon unified memory — a generation test that starts with Ollama
models resident can be evicted mid-render, so the sections evict before
running. The `_mcp` helper is the one MCP-call path every section uses,
recording PASS/WARN/FAIL with the reason; the watchdog prints progress for
long generations so a 40-minute render does not look hung.

## Interfaces

`_mcp`, `_chat`, `_comfyui_get`/`_comfyui_post`, `_wait_for_comfyui_queue`,
`_wait_for_comfyui_idle`, `_clear_comfyui_queue`, `_free_memory_for_comfyui`,
`_comfyui_watchdog`, and the re-exported `record`/`R`/`_emit` result
surface.

## Gotchas

The `.env` loader has a hermetic-test guard (`UNIT_TEST_MODE=1` skips
loading) so the unit tests do not inherit a developer's environment. The
URLs replace `host.docker.internal` with `localhost` because a containerized
reference must not leak into the host run.
