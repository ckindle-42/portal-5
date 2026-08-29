---
id: unit-HOWTO-5-code-generation-execution
kind: why
title: "HOWTO \u2014 5. Code Generation & Execution"
sources:
- type: code
  path: portal/modules/coding/tools/code_sandbox_mcp.py
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.840412
updated_at: 1783195000.840412
---

**What:** Generate code with AI and execute it in an isolated Docker-in-Docker sandbox.

**Activate:** Select `Portal Code Expert` (`auto-coding`) from the model dropdown. Its `tools` list in `config/portal.yaml` grants `execute_python`, `execute_nodejs`, `execute_bash`, and `sandbox_status`; the sandbox MCP's full surface also includes `execute_powershell` and the session tools `list_sessions` / `reset_session` (manifest: `config/inference/tools_manifest_code_sandbox_mcp.json`). Sessions persist an interpreter between calls, so long tasks keep state instead of re-seeding a throwaway container each time.

**How:** Execution runs through `portal/modules/coding/tools/code_sandbox_mcp.py`, the sandbox MCP server on the `portal5-mcp-sandbox` container. Each tool launches a throwaway container from an image (`python:3.11-slim`, `node:20-alpine`, `alpine:latest` by default) inside the Docker-in-Docker daemon, with a default `SANDBOX_TIMEOUT` of 30 seconds, no network (`SANDBOX_ALLOW_NETWORK=false`), and a small memory ceiling.

Environment knobs live in `.env`: `SANDBOX_TIMEOUT`, `SANDBOX_ALLOW_NETWORK`, and `SANDBOX_LAB_EXEC`. The last one swaps in the attack-image lab envelope used by the `-exec` security variants, widening the timeout and enabling a routable lab network (`$LAB_TARGET_*`). Pass an explicit `timeout` argument per call when a task may run long; the ceiling is enforced by the server, not the caller.

## Why

Code execution must never touch the host directly, so the sandbox MCP shells out to a Docker-in-Docker daemon with throwaway containers, a strict default timeout, and networking disabled by default. Because the isolation posture is expressed as env flags rather than hardcoded, the same tool surface serves both the locked-down default lane and the authorized lab-exec lane without duplicating handlers.
