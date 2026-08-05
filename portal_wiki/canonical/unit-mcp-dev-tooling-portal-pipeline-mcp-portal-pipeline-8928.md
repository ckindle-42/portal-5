---
id: unit-mcp-dev-tooling-portal-pipeline-mcp-portal-pipeline-8928
kind: what
title: "MCP_DEV_TOOLING \u2014 Portal Pipeline MCP (`portal-pipeline`, `:8928`)"
sources:
- type: code
  path: portal/platform/mcp_host/pipeline_mcp.py
- type: code
  path: scripts/native-mcp-service.sh
- type: code
  path: scripts/lib/util.sh
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.571575
updated_at: 1784946220.571575
---

The pipeline MCP is a host-native MCP SDK v2 server on port 8928 (overridable via
`PIPELINE_MCP_PORT`). `./launch.sh up` starts it through `_ensure_native_mcp_service`
in `scripts/lib/util.sh`, which on macOS registers a launchd agent that runs
`scripts/native-mcp-service.sh pipeline-mcp` — itself a thin exec of
`python -m portal.platform.mcp_host.pipeline_mcp`. The server runs its own
streamable-HTTP app and imports nothing from `portal.platform.inference`; every tool
reads live data by calling the pipeline's HTTP endpoints. It is registered in
`.mcp.json` so Claude Code and opencode pick it up automatically.

## Why

Being host-native rather than a container gives the pipeline MCP direct access to the
repo tree and the local pipeline without volume mounts or networking, and the
zero-import rule keeps the coding-tools surface decoupled from the inference stack.
The launchd wrapper makes it start and stop with the stack, so the IDE tools are
simply there when the project is up.
