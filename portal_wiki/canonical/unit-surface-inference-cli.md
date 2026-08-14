---
id: unit-surface-inference-cli
kind: mixed
title: "Portal operator CLI \u2014 typed command surface"
sources:
- type: code
  path: portal/platform/inference/cli/*.py
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- cli
created_at: 1785885000.0
updated_at: 1785885000.0
---

The `portal` CLI is the typed operator surface for Portal 5, composed in one place: `_apps.py` holds a shared typer app per command group, the `__init__` mounts them with the maintenance commands onto the root `app`, and `__main__` is a three-line delegate so `python -m portal.platform.inference.cli` runs the same root. A `register` hook lets modules add commands without platform internals depending on them.

## Why

An operator CLI must be typed and predictable, and one composition root keeps it coherent. Centralising the shared apps and the Ollama helpers means every command addresses the same backend, native binary or docker-exec, and no sub-module import cycle can form — the same plugin-into-host shape the MCP fleet uses, where modules contribute commands without platform internals knowing them.

## Interfaces

`_apps.py` exports `config_app`, `workspace_app`, `models_app`, `module_app`, `agent_app`. The groups are `config` (`config_validate`, `config_show`), `models` (dual-origin provisioning via `_pull_native` and `_pull_hf_model`), `workspace` (`workspace_init`, `workspace_status`), `module` (confirm-gated toggling with blast-radius counts), and `agent` (`agent_explain`, `agent_proposed`). Top-level maintenance adds `sync_config`, `cmd_test`, and `cmd_update`, with `_detect_ollama_cmd` resolving the backend for every model-facing command.

## Gotchas

The agent surface has no `run` command by design — a real engagement needs a module-supplied `provider` and `executor`, so `explain` is the honest dry-run until slice-2 wiring lands. Module toggling changes routing, not processes: MCP servers keep running. `test` requires a live stack, `update` touches the running stack, and config validation here is the fast check, not the full harness.
