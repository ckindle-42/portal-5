---
id: unit-surface-inference-cli
kind: mixed
title: "Portal operator CLI \u2014 typed command surface"
sources:
- type: code
  path: portal/platform/inference/cli/*.py
- type: code
  path: portal/platform/inference/cli/trace/*.py
claims:
- probe: repo.path.exists
  path: portal/platform/inference/cli/*.py
  equals: true
confidence: high
tags:
- authored-v1
- platform
- inference
- cli
---

The `portal` CLI is the typed operator surface for Portal 5, composed in one place: `_apps.py` holds a shared typer app per command group, the `__init__` mounts them with the maintenance commands onto the root `app`, and `__main__` is a three-line delegate so `python -m portal.platform.inference.cli` runs the same root. A `register` hook lets modules add commands without platform internals depending on them.

## Why

An operator CLI must be typed and predictable, and one composition root keeps it coherent. Centralising the shared apps and the Ollama helpers means every command addresses the same backend, native binary or docker-exec, and no sub-module import cycle can form — the same plugin-into-host shape the MCP fleet uses, where modules contribute commands without platform internals knowing them.

## Interfaces

`_apps.py` exports `config_app`, `workspace_app`, `models_app`, `module_app`, `agent_app`. The groups are `config` (`config_validate`, `config_show`), `models` (dual-origin provisioning via `_pull_native` and `_pull_hf_model`), `workspace` (`workspace_init`, `workspace_status`), `module` (confirm-gated toggling with blast-radius counts), and `agent` (`agent_explain`, `agent_proposed`). Top-level maintenance adds `sync_config`, `cmd_test`, `cmd_trace`, `cmd_update` and the trace rag seed (`trace-seed-rag`), with `_detect_ollama_cmd` resolving the backend for every model-facing command.

## Trace

`portal trace` is the read-only, hop-by-hop check of a running install: the command never changes state, and a section that cannot run reports WARN with its reason rather than passing silently. `--section` takes a section key, its 1-based number or a key prefix and is repeatable; `--json` emits the same report as data. The sections are `host` (host services), `containers` (each running container against its own image, plus the sandbox images `portal5-dind` must serve — resolved from the MCP containers' own env, FAIL naming any missing), `workspaces` (one streamed turn per production seat — each non-bench workspace and its declared variants — end to end), `pins` (code-level model pins and the served catalogue), `aliases` (deprecated aliases), `engines` (oMLX and Ollama surfaces), `owui` (the Open WebUI tool path) and `lab` (Splunk auth, a hunt query and one labelled event, from the security module).

`portal trace-seed-rag` is the one seed the rag hop needs when no knowledge base holds chunks: it copies a fixed set of real `docs/` markdown into the RAG MCP's own KB sources volume and ingests it through the MCP's own `kb_ingest` (`rebuild=True`, dedicated `portal-trace-docs` kb id), so re-running produces the same KB. Seat turns send no client `max_tokens`: the router applies each seat's declared output budget from config, so a reasoning seat is graded under its own budget rather than a fixed trace cap, and a turn that still ends inside reasoning is a FAIL naming that budget (product defect: think flag or template).

The hops added in 2026-11-18 assert live what the trimmed offline tests had asserted against mocks. `pins` compares the running Pipeline's `GET /v1/models` with the config: every enabled workspace and every OWUI-exposed variant is advertised under its declared name and nothing undeclared is. `aliases` runs one turn per deprecated alias in `config/portal.yaml` and requires the router's `x-portal-route` header to name the alias's declared target (a disabled target or an exhausted budget is WARN, never a pass). `workspaces` requires that, after the first seat an engine serves, that engine's own resident list (oMLX `/v1/models/status`, Ollama `/api/ps`) names the model — the route header alone cannot tell "the router says omlx-coding" from "oMLX ran it". `owui` runs one native Open WebUI turn on a tool seat and requires the sandbox-only value in the answer plus a Pipeline `/v1/trace` record for that turn naming the seat, its backend and a tool call; Open WebUI renders the tool call itself in its native flow, so the Pipeline's text receipt is optional and the trace hop's `tool_calls` is the proof the tool ran.

## Gotchas

The agent surface has no `run` command by design — a real engagement needs a module-supplied `provider` and `executor`, so `explain` is the honest dry-run until slice-2 wiring lands. Module toggling changes routing, not processes: MCP servers keep running. `test` requires a live stack, `update` touches the running stack, and config validation here is the fast check, not the full harness.
