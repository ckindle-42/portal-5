---
id: unit-mcp-dev-tooling-mcp-servers-mcp-json
kind: what
title: "MCP_DEV_TOOLING \u2014 MCP Servers (`.mcp.json`)"
sources:
- type: code
  path: .mcp.json
- type: code
  path: config/portal.yaml
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.570611
updated_at: 1784946220.570611
---

`.mcp.json` is the MCP server roster consumed by Claude Code. Four entries are
command-transport servers launched through `npx` or `uvx`: `filesystem`, `fetch`,
`git`, and `docker`. The rest are remote HTTP servers pointing at the reserved
portal-* ports — comfyui :8910, documents :8913, sandbox :8914, tts :8916,
security :8919, memory :8920, rag :8921, research :8922, browser :8923,
proxmox :8927, pipeline :8928, mitre :8929, wiki :8931, and detections :8932 among
them — so each tool set is available to the client without a local install.

## Why

The roster is the single place Claude Code learns which capabilities exist, and its
shape mirrors the project's port reservation table: every portal-* server is an HTTP
endpoint on a fixed port with no per-client packaging. That keeps tool delivery
cheap and makes the list auditable against `config/portal.yaml`'s fleet table.
