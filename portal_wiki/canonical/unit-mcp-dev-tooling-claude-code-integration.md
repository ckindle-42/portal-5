---
id: unit-mcp-dev-tooling-claude-code-integration
kind: what
title: "MCP_DEV_TOOLING \u2014 Claude Code Integration"
sources:
- type: code
  path: scripts/cc-portal.sh
- type: code
  path: scripts/cc-local.sh
- type: code
  path: scripts/cc-stock.sh
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5759969
updated_at: 1784946220.5759969
---

Claude Code has three operating modes with Portal 5, each a thin wrapper script
around the `claude` CLI. Mode A (`scripts/cc-portal.sh`) keeps Anthropic cloud as
the intelligence and adds Portal tools via `.mcp.json`. Mode B (`scripts/cc-local.sh`)
points `ANTHROPIC_BASE_URL` at the pipeline on :9099 so local models supply the
intelligence, and Mode C (`scripts/cc-stock.sh`) runs vanilla cloud Claude Code with
zero Portal MCP servers via the strict-mcp-config bypass. All three launch from the
repo root so `.mcp.json` and `CLAUDE.md` are discovered automatically unless
explicitly bypassed.

## Why

One tool, three intents: cloud with Portal tooling, fully local inference, and
pristine stock behaviour. Keeping each intent in its own script means the operator
picks a mode by name and never has to remember the environment variables or the
CLI flags that implement it, and none of the modes rename or delete the project's
config files to switch.
