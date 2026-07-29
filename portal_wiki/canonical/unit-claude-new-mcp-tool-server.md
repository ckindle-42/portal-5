---
id: unit-claude-new-mcp-tool-server
kind: why
title: "CLAUDE.md \u2014 New MCP Tool Server"
sources:
- type: design
  path: CLAUDE.md
  section: New MCP Tool Server
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1785348301.194376
updated_at: 1785348301.194376
---

1. Create `portal/modules/<discipline>/tools/<name>_mcp.py` (or `portal/platform/<area>/` for a cross-cutting server — see Rule 6)
2. Add service to `deploy/portal-5/docker-compose.yml` on an unused port (Rule 7)
3. Add the server to `config/portal.yaml` under `mcp_fleet:` with the canonical `id`, `name`, `port`, and flags
4. Run `./launch.sh sync-config` — regenerates `.mcp.json` and OWUI tool preset stubs
5. Add tool JSON to `imports/openwebui/tools/portal_<name>.json`
6. `openwebui_init.py` picks up new tool servers automatically from the fleet
7. Reconcile bound docs and re-stamp: `python3 scripts/doc_ledger.py status` → fix → stamp
