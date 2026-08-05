---
id: unit-mcp-dev-tooling-security-boundaries
kind: what
title: "MCP_DEV_TOOLING \u2014 Security Boundaries"
sources:
- type: code
  path: .mcp.json
- type: code
  path: portal/modules/coding/tools/code_sandbox_mcp.py
- type: code
  path: portal/platform/mcp_host/pipeline_mcp.py
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.580513
updated_at: 1784946220.580513
---

Each MCP server in `.mcp.json` has an explicit boundary. `filesystem` is launched
with `${HOME}/projects` and `/tmp` as its allowed roots. `docker` reaches the Docker
socket, which is acceptable only on a single-user machine. `fetch` performs HTTP
requests and should not be pointed at administrative APIs. `portal-sandbox` runs code
in an isolated container (`code_sandbox_mcp.py`) whose posture widens only when
`SANDBOX_LAB_EXEC` is set. `portal-pipeline` binds localhost and authenticates with
`PIPELINE_API_KEY`. There is deliberately no sqlite server: the Open WebUI database
lives in the `open-webui-data` named volume rather than a host bind mount.

## Why

The boundaries are the trust model for a local, single-operator setup, and they are
stated explicitly because each server is a different kind of surface. Reading them
together shows which servers are sandboxed, which inherit host trust, and which are
read-only — the information an operator needs before granting a coding agent broader
access or exposing a port.
