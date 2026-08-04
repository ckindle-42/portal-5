---
id: unit-mcp-dev-tooling-mode-c-stock-cloud-zero-portal-mcp-cc-stock-sh
kind: what
title: "MCP_DEV_TOOLING \u2014 Mode C \u2014 Stock cloud (zero Portal MCP, `cc-stock.sh`)"
sources:
- type: code
  path: scripts/cc-stock.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.577482
updated_at: 1784946220.577482
---

Mode C runs vanilla cloud Claude Code inside the repo with none of Portal's MCP
servers. `scripts/cc-stock.sh` builds the argument list starting with
`--strict-mcp-config`, which tells Claude Code to load only command-line MCP servers
and ignore all file-based ones, so `.mcp.json` stays in place untouched. By default
the inline config is empty; setting `CC_STOCK_KEEP_GENERIC` adds back only the four
non-Portal servers (filesystem, fetch, git, docker), and setting
`CC_STOCK_IGNORE_SETTINGS` appends `--setting-sources user` to also skip project and
local settings.

## Why

Stock mode exists because occasionally the operator wants pristine cloud Claude Code
— no sandbox, no pipeline tools, no project config influence — without modifying the
repo. The strict-mcp-config flag delivers exactly that, and the two environment
switches give a graduated path from zero MCP to the generic-only subset without ever
touching a file.
