---
id: unit-HOWTO-adding-new-capabilities
kind: why
title: "HOWTO \u2014 Adding new capabilities"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: config/backends.yaml
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: portal/platform/wiki/adapters/seed_facts.py
- type: code
  path: portal/platform/inference/sync_config.py
last_generated_commit: 956ee226e319e701e3605c9de6950bfa437a56f0
claims: []
confidence: high
tags:
- HOWTO
- checklist
- docs
- verified-v1
created_at: 1785464185.5918112
updated_at: 1785464185.5918112
---

# Adding new capabilities

Checklists for extending Portal 5 with a new MCP tool server, persona, workspace routing tier, or cluster node.

## New MCP Tool Server
1. Create `portal/modules/<discipline>/tools/<name>_mcp.py`, or for a
   platform-owned server use `portal/platform/<area>/` (e.g. `memory` at
   `portal/platform/memory/`) — the `module:` tag on the fleet entry is
   what assigns ownership (see CLAUDE.md Rule 6).
2. Add the service to `deploy/portal-5/docker-compose.yml` on an unused port (Rule 7).
3. Add the server to `config/portal.yaml` under `mcp_fleet:` with the canonical `id`, `name`, `port`, and flags.
4. Run `./launch.sh sync-config` — regenerates `.mcp.json` and the OWUI workspace presets.
5. Add tool JSON to `imports/openwebui/tools/portal_<name>.json`.
6. `openwebui_init.py` registers tool servers from the fleet-derived `.mcp.json` automatically.
7. Reconcile the wiki: `./launch.sh sync-config` refreshes fact-units and
   generated doc blocks; validate check AW (`scripts/validate_system.py`)
   catches any that drifted. Edit authored units directly.

## New Persona
1. Create `config/personas/<slug>.yaml` with: `name`, `slug`, `module`, `workspace_model`, `category`, and one of `system_prompt`/`prompt_template`.
2. `openwebui_init.py` creates the Open WebUI model preset on next seed.
3. No other changes needed.
4. Reconcile the wiki: fact-units like `unit-fact-persona-roster`
   regenerate on `./launch.sh sync-config`; AW verifies they match live config.

## New Workspace Routing Tier
1. Add the workspace entry to `config/portal.yaml` under `workspaces:`.
2. Run `./launch.sh sync-config` — regenerates `backends.yaml workspace_routing`, OWUI preset JSON, and `.mcp.json`.
3. Verify: `python3 -m pytest tests/unit/test_generated_artifacts_fresh.py -q`.
4. Do NOT hand-edit `backends.yaml workspace_routing` or `imports/openwebui/workspaces/` — those are generated.
5. Reconcile the wiki via `sync-config` + AW, per the earlier checklists.

## New Cluster Node
1. Edit `config/backends.yaml` — add backend entry, assign to group.
2. `docker compose restart portal-pipeline`.
3. Done. No code changes.
4. Reconcile the wiki via `sync-config` + AW, per the earlier checklists.

## Why

These four checklists share one rule: every capability lands as a config
edit plus a regeneration step, never as scattered hand-edits to derived
files. `config/portal.yaml` is the single source for workspaces and the
MCP fleet, `config/backends.yaml` is the single source for backends and
groups, and `sync-config` mechanically rewrites `workspace_routing`,
`.mcp.json`, and the OWUI presets from them — which is why the older
commit-stamp ledger re-stamp step is gone: doc currency is now enforced
by AW comparing each fact-unit and generated block against live config
after `sync-config`, and by the drift census, not by a stamp run. The
cluster-node checklist is intentionally the shortest because a backend
entry is just data under Rule 1.
