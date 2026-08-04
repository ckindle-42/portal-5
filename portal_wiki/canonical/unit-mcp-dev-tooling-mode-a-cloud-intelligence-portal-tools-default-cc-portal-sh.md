---
id: unit-mcp-dev-tooling-mode-a-cloud-intelligence-portal-tools-default-cc-portal-sh
kind: what
title: "MCP_DEV_TOOLING \u2014 Mode A \u2014 Cloud intelligence + Portal tools (default,\
  \ `cc-portal.sh`)"
sources:
- type: code
  path: scripts/cc-portal.sh
- type: code
  path: .mcp.json
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.576541
updated_at: 1784946220.576541
---

Mode A is the default Claude Code posture: Anthropic cloud supplies the reasoning,
and Portal 5 supplies tools. `scripts/cc-portal.sh` runs `claude` from the repo
root so `.mcp.json` and `CLAUDE.md` are auto-discovered, and it exports
`PIPELINE_API_KEY` from `.env` so the portal tools that reach the pipeline are
authenticated. The equivalent manual launch is plain `claude` from the root. The
tool namespaces available come straight from `.mcp.json`: the filesystem, git,
docker, and fetch servers plus the portal-sandbox and portal-pipeline HTTP servers.

## Why

This mode exists to give the strongest available reasoning model access to Portal's
operational surface — the sandbox, the pipeline introspection tools, and the repo
filesystem — without any of that intelligence being replaced. It is the default
because it needs no model routing configuration; the tools are simply present and
the cloud model uses them.
