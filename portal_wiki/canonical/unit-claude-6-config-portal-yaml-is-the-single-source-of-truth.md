---
id: unit-claude-6-config-portal-yaml-is-the-single-source-of-truth
kind: why
title: "CLAUDE.md \u2014 6 \u2014 config/portal.yaml Is the Single Source of Truth\
  \ for Workspaces and MCP Fleet"
sources:
- type: design
  path: CLAUDE.md
  section: "6 \u2014 config/portal.yaml Is the Single Source of Truth for Workspaces\
    \ and MCP Fleet"
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.8075058
updated_at: 1783195000.8075058
---


All workspaces and the MCP tool server fleet are defined in **`config/portal.yaml`**. Do not hand-edit these derived files:
- `config/backends.yaml` → `workspace_routing` block (auto-generated)
- `.mcp.json` → IDE MCP server list (auto-generated)
- `imports/openwebui/workspaces/workspace_*.json` → OWUI workspace presets (auto-generated)

After any change to `config/portal.yaml`, regenerate all derived files:
```bash
./launch.sh sync-config
