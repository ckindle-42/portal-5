---
id: unit-mcp-dev-tooling-adding-a-feature-opencode-with-local-laguna
kind: what
title: "MCP_DEV_TOOLING \u2014 Adding a feature (opencode with local Laguna)"
sources:
- type: code
  path: portal/platform/mcp_host/pipeline_mcp.py
- type: code
  path: config/portal.yaml
- type: code
  path: config/personas/codingagentic.yaml
last_generated_commit: 64c5f5f41652bf67e97863ee1a6285289eaeea00
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.578677
updated_at: 1784946220.578677
---

Adding a new workspace with opencode and the local Laguna persona follows the
agentic loop that the `laguna` variant's `system_prompt_append` in `config/portal.yaml`
bakes into every turn. First call `explore_repository` (FastContext) to learn how
workspaces are defined and which files the routing touches, then use `read_text_file`
and `write_file` from `portal/platform/mcp_host/pipeline_mcp.py` to make the change,
and finally run the unit suite with `execute_bash` in the sandbox. The workspace
definition itself lands in `config/portal.yaml` and is consumed by the routing layer.

## Why

The loop exists because a new workspace is a real configuration change: it must match
the shape the router expects or every request for it mis-routes. Making exploration,
edit, and verification explicit steps forces the model to confirm the exact definition
shape before writing anything, which keeps a one-file addition from becoming a
routing incident.
