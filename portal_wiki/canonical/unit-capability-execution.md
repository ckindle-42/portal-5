---
id: unit-capability-execution
kind: mixed
title: "Execution MCP \u2014 session-managed isolated code sandbox"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/coding/tools/code_sandbox_mcp.py
- type: code
  path: config/inference/tools_manifest_code_sandbox_mcp.json
claims: []
confidence: high
tags:
- capability
- mcp
- coding
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Execution MCP — session-managed isolated code sandbox

## What

The Execution MCP (`portal/modules/coding/tools/code_sandbox_mcp.py`, port
8914) runs code in an isolated Docker-in-Docker sandbox on the
`portal5-sandbox` container. It is pipeline- and IDE-exposed and backs the
`auto-coding` workspace.

## How it's used

`execute_python`, `execute_nodejs`, `execute_bash`, and `execute_powershell`
each launch a throwaway container from its runtime image (`python:3.11-slim`,
`node:20-alpine`, `alpine:latest`, pwsh). `sandbox_status` reports readiness;
`list_sessions` and `reset_session` manage the session lifecycle — a session
persists an interpreter between calls, so a long task keeps its state instead
of re-seeding a container each time. The default posture is no network, a
`SANDBOX_TIMEOUT` of 30 seconds, and a small memory ceiling, all expressed as
env flags.

## Why it exists

Code execution must never touch the host directly, so the sandbox shells out to
a DinD daemon with throwaway containers. Because the isolation posture is env
flags rather than hardcoded, the same tool surface serves both the locked-down
default lane and the authorized `SANDBOX_LAB_EXEC` attack-image lane without
duplicating handlers.

## Value

A persona can run real code — scripts, data munging, security tools — and keep
interpreter state across a multi-step task, with the guarantee that nothing
escapes the container boundary. The session surface is what makes multi-call
agentic workflows viable where a fresh container per call would lose all
working state.
