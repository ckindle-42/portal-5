---
id: unit-mcp-dev-tooling-what-opencode-gets
kind: what
title: "MCP_DEV_TOOLING \u2014 What opencode gets"
sources:
- type: code
  path: opencode.jsonc
- type: code
  path: portal/platform/mcp_host/pipeline_mcp.py
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.573175
updated_at: 1784946220.573175
---

Opening the repo with opencode delivers three things. First, fully local inference:
every completion goes through the `portal` provider in `opencode.jsonc` to the
pipeline on :9099 and then to Ollama, so no tokens leave the machine. Second, the
workspace and persona catalog as models: `GET /v1/models` advertises the base
workspaces plus the `ide_expose` personas, with a curated subset in the provider
`models` block and `portal/codingagentic` as the default. Third, the full MCP roster
declared in the opencode `mcp` block — the same HTTP servers the pipeline exposes.
Cloud providers are disabled in the same file to prevent accidental cloud use.

## Why

The point of the integration is that an IDE session should inherit the project's
local-first posture without configuration: local provider, local models, local tools,
cloud locked out. Stating what opencode actually receives makes it possible to verify
that posture from the config alone, which is the difference between a claimed local
setup and a real one.
