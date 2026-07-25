---
id: unit-mcp-dev-tooling-mode-c-stock-cloud-zero-portal-mcp-cc-stock-sh
kind: what
title: "MCP_DEV_TOOLING \u2014 Mode C \u2014 Stock cloud (zero Portal MCP, `cc-stock.sh`)"
sources:
- type: doc
  path: docs/MCP_DEV_TOOLING.md
  commit: 05e42ec2
  section: "Mode C \u2014 Stock cloud (zero Portal MCP, `cc-stock.sh`)"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.577482
updated_at: 1784946220.577482
---

```bash
scripts/cc-stock.sh             # stock: claude --strict-mcp-config --mcp-config '{}' (zero MCP)
CC_STOCK_KEEP_GENERIC=1 scripts/cc-stock.sh   # stock intelligence, keep filesystem/git/fetch/docker
CC_STOCK_IGNORE_SETTINGS=1 scripts/cc-stock.sh  # also ignore project/local settings
```

`--strict-mcp-config` makes Claude Code use only command-line MCP servers and ignore all
file-based ones, so `.mcp.json` stays in place untouched.

---
