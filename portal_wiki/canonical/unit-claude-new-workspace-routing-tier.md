---
id: unit-claude-new-workspace-routing-tier
kind: why
title: "CLAUDE.md \u2014 New Workspace Routing Tier"
sources:
- type: design
  path: CLAUDE.md
  section: New Workspace Routing Tier
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.810251
updated_at: 1783195000.810251
---

1. Add the workspace entry to `config/portal.yaml` under `workspaces:`
2. Run `./launch.sh sync-config` — regenerates `backends.yaml workspace_routing`, OWUI preset JSON, and `.mcp.json`
3. Verify: `python3 -m pytest tests/unit/test_generated_artifacts_fresh.py -q`
4. Do NOT hand-edit `backends.yaml workspace_routing` or `imports/openwebui/workspaces/` — those are generated
