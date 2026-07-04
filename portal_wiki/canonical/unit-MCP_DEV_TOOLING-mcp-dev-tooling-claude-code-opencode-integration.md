---
id: unit-MCP_DEV_TOOLING-mcp-dev-tooling-claude-code-opencode-integration
kind: why
title: "MCP_DEV_TOOLING \u2014 MCP Dev Tooling \u2014 Claude Code & opencode Integration"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: "MCP Dev Tooling \u2014 Claude Code & opencode Integration"
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.87017
updated_at: 1783195000.87017
---


Portal 5 ships two configuration files that wire it into AI-powered coding tools:

- **`.mcp.json`** — MCP server roster, picked up automatically by Claude Code (not opencode — see `opencode.jsonc` `mcp` block)
- **`opencode.jsonc`** — opencode provider config, points opencode at the local pipeline as its AI backend

These let Claude Code and opencode read the repo, run code, call Portal 5 tools, and (for opencode)
use fully local Portal 5 models instead of any cloud API.

---
