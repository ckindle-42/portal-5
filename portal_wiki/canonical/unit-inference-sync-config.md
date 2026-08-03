---
id: unit-inference-sync-config
kind: mixed
title: "Inference sync_config \u2014 single-source artifact generator"
sources:
- type: code
  path: portal/platform/inference/sync_config.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
created_at: 1785797766.391104
updated_at: 1785797766.391104
---

`sync_config.py` is the single-source-of-truth generator: it reads
`config/portal.yaml` and emits every derived artifact — the workspace routing
block in `config/backends.yaml`, `.mcp.json`, the opencode picker, the
Open WebUI workspace presets, and the module manifest. It is idempotent by
contract, which is what lets CI verify it.

## Why

Rule 6 makes `portal.yaml` the source of truth and every other config file a
derived artifact that must not be hand-edited. This module is the generator
that enforces that: edit the YAML, run sync-config, and every derived file
follows. Idempotence is the load-bearing property — running it twice must
produce no diff, because that is what the pre-commit freshness gate and the
test suite assert. Each emitter owns one artifact, and the emitters are
structured so adding a new derived file is one function.

## Interfaces

`emit_workspace_routing` writes the backends routing block;
`emit_mcp_json` writes `.mcp.json`; `emit_opencode_picker` writes the
opencode config; `emit_owui_presets` writes the OWUI workspace presets;
`emit_module_manifest` writes the module state; `main` runs them all.

## Gotchas

The generated files must never be hand-edited — a manual change is
overwritten on the next sync-config, and the pre-commit gate fails until the
edit is reverted or moved into `portal.yaml`.
