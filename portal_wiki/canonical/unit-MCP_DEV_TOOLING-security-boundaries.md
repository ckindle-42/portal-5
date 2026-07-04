---
id: unit-MCP_DEV_TOOLING-security-boundaries
kind: why
title: "MCP_DEV_TOOLING \u2014 Security Boundaries"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: Security Boundaries
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.8752158
updated_at: 1783195000.8752158
---


- `filesystem` is scoped to the repo dirs and `~/.portal5/logs` only — cannot reach outside.
- `docker` uses the Docker socket. Acceptable on a local single-user machine only.
- `fetch` is read-only HTTP GET. Do not use it to POST to the Open WebUI admin API.
- `portal-sandbox` runs commands in an isolated container. `SANDBOX_LAB_EXEC=true` expands
  capabilities for lab pentest workflows — see `docs/LAB_SETUP.md`.
- `portal-pipeline` is localhost-only. Reads `PIPELINE_API_KEY` from the environment to
  authenticate calls to the pipeline.

> **sqlite server omitted:** Open WebUI's `webui.db` lives in a Docker volume not bind-mounted
> to the host. To enable sqlite MCP, add a bind mount in `docker-compose.yml` and add the
> entry back to `.mcp.json`.
