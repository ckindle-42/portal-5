---
id: unit-MCP_DEV_TOOLING-mode-c-stock-cloud-zero-portal-mcp-cc-stock-sh
kind: why
title: "MCP_DEV_TOOLING \u2014 Mode C \u2014 Stock cloud (zero Portal MCP, `cc-stock.sh`)"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: "Mode C \u2014 Stock cloud (zero Portal MCP, `cc-stock.sh`)"
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.873475
updated_at: 1783195000.873475
---


```bash
scripts/cc-stock.sh             # stock: claude --strict-mcp-config --mcp-config '{}' (zero MCP)
CC_STOCK_KEEP_GENERIC=1 scripts/cc-stock.sh   # stock intelligence, keep filesystem/git/fetch/docker
CC_STOCK_IGNORE_SETTINGS=1 scripts/cc-stock.sh  # also ignore project/local settings
```

`--strict-mcp-config` makes Claude Code use only command-line MCP servers and ignore all
file-based ones, so `.mcp.json` stays in place untouched.

---
