---
id: unit-mcp-dev-tooling-mcp-dev-tooling-claude-code-opencode-integration
kind: what
title: "MCP_DEV_TOOLING \u2014 MCP Dev Tooling \u2014 Claude Code & opencode Integration"
sources:
- type: code
  path: .mcp.json
- type: code
  path: opencode.jsonc
last_generated_commit: 925f52c4b7e7ec876ea24823d3a221c7f2f8f505
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.570229
updated_at: 1784946220.570229
---

Portal 5 ships two root-level configuration files that wire AI coding tools into the
stack. `.mcp.json` is the MCP server roster that Claude Code auto-discovers when it
opens the repo, covering the local transport servers and the remote portal-* HTTP
servers. `opencode.jsonc` is the opencode configuration: it declares the local
pipeline as the provider, the key plumbing for `PIPELINE_API_KEY`, the cloud-provider
guard, and its own `mcp` block — opencode reads tool servers from that block, not
from `.mcp.json`. Together they let both clients read the tree, run code, call Portal
tools, and, for opencode, use fully local models.

## Why

The two files exist because the two clients have different configuration surfaces:
Claude Code consumes `.mcp.json` natively, while opencode needs a provider block and
its own MCP roster. Keeping them separate but in lockstep means each tool reads the
format it expects and the integration stays declarative rather than scripted.
