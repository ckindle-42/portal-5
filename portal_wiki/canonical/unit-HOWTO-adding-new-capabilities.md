---
id: unit-HOWTO-adding-new-capabilities
kind: why
title: "HOWTO — Adding new capabilities"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: config/personas
- type: code
  path: config/backends.yaml
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
- checklist
created_at: 1785464185.5918112
updated_at: 1785464185.5918112
---

# Adding new capabilities

Checklists for extending Portal 5 with a new MCP tool server, persona, workspace routing tier, or cluster node.

## New MCP Tool Server
1. Create `portal/modules/<discipline>/tools/<name>_mcp.py` (or `portal/platform/<area>/` for a cross-cutting server — see CLAUDE.md Rule 6)
2. Add service to `deploy/portal-5/docker-compose.yml` on an unused port (Rule 7)
3. Add the server to `config/portal.yaml` under `mcp_fleet:` with the canonical `id`, `name`, `port`, and flags
4. Run `./launch.sh sync-config` — regenerates `.mcp.json` and OWUI tool preset stubs
5. Add tool JSON to `imports/openwebui/tools/portal_<name>.json`
6. `openwebui_init.py` picks up new tool servers automatically from the fleet
7. Reconcile bound docs and re-stamp: `python3 scripts/doc_ledger.py status` → fix → stamp

## New Persona
1. Create `config/personas/<slug>.yaml` with: `name`, `slug`, `module`, `workspace_model`, `category`, and one of `system_prompt`/`prompt_template`
2. `openwebui_init.py` creates the Open WebUI model preset on next seed
3. No other changes needed
4. Reconcile bound docs and re-stamp: `python3 scripts/doc_ledger.py status` → fix → stamp

## New Workspace Routing Tier
1. Add the workspace entry to `config/portal.yaml` under `workspaces:`
2. Run `./launch.sh sync-config` — regenerates `backends.yaml workspace_routing`, OWUI preset JSON, and `.mcp.json`
3. Verify: `python3 -m pytest tests/unit/test_generated_artifacts_fresh.py -q`
4. Do NOT hand-edit `backends.yaml workspace_routing` or `imports/openwebui/workspaces/` — those are generated
5. Reconcile bound docs and re-stamp: `python3 scripts/doc_ledger.py status` → fix → stamp

## New Cluster Node
1. Edit `config/backends.yaml` — add backend entry, assign to group
2. `docker compose restart portal-pipeline`
3. Done. No code changes.
4. Reconcile bound docs and re-stamp: `python3 scripts/doc_ledger.py status` → fix → stamp
