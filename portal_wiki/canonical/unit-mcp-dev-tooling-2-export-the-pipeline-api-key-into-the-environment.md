---
id: unit-mcp-dev-tooling-2-export-the-pipeline-api-key-into-the-environment
kind: what
title: "MCP_DEV_TOOLING \u2014 2. Export the pipeline API key into the environment"
sources:
- type: code
  path: .env.example
- type: code
  path: scripts/cc-portal.sh
- type: code
  path: scripts/cc-local.sh
- type: code
  path: opencode.jsonc
- type: code
  path: portal/platform/mcp_host/pipeline_mcp.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.574263
updated_at: 1784946220.574263
---

The pipeline requires a bearer token on its authenticated endpoints. The key lives as
`PIPELINE_API_KEY` in `.env` (see `.env.example`), and every entry point that talks
to the pipeline must carry it. `scripts/cc-portal.sh` and `scripts/cc-local.sh`
grep the value out of `.env` and export it before launching `claude`, and
`opencode.jsonc` declares `PIPELINE_API_KEY` in its provider `env` block so opencode
passes it as the bearer token. The pipeline MCP reads the same variable through
`_pipeline_headers` in `portal/platform/mcp_host/pipeline_mcp.py` to authenticate
its own calls.

## Why

The API key is the only guard between localhost callers and the routing stack, and it
is deliberately kept out of source control. Centralising the export in the wrapper
scripts and the provider config means an operator never has to paste the secret into
a shell by hand, which is both a convenience and a way to avoid leaking it into a
history or a log.
