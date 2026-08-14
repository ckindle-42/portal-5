---
id: unit-mcp-dev-tooling-1-ensure-stack-is-running
kind: what
title: "MCP_DEV_TOOLING \u2014 1. Ensure stack is running"
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/lib/util.sh
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.573901
updated_at: 1784946220.573901
---

Every Portal MCP tool is a thin client that proxies to live services, so the stack
must be up before anything works. `./launch.sh up` (the `up` case in `launch.sh`)
first pulls the Docker images, then calls `_ensure_native_services` from
`scripts/lib/util.sh` to start the host-native MCP servers — including
`pipeline-mcp` on :8928 — and finally brings up the compose stack with the pipeline
on :9099 and the sandbox container on :8914. Both the pipeline and Ollama on :11434
have to answer before portal tools can route a request.

## Why

The pipeline MCP and sandbox MCP hold no state of their own; they forward every call
to the pipeline, Ollama, or an isolated container. Treating `./launch.sh up` as a
mandatory first step keeps health checks from failing at the network layer, which is
exactly the failure the tooling workflow is designed to avoid.
