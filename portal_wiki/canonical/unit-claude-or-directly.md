---
id: unit-claude-or-directly
kind: why
title: "CLAUDE.md \u2014 or directly:"
sources:
- type: design
  path: CLAUDE.md
  section: 'or directly:'
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1785348301.194344
updated_at: 1785348301.194344
---

python3 -m portal.platform.inference.sync_config
```

`sync-config` is idempotent — running it twice produces no diff. The test suite (`tests/unit/test_generated_artifacts_fresh.py`) verifies this. `sync-config` also regenerates `config/modules.generated.yaml`, a rendered snapshot of module enable/disable state (see Rule 12's sibling discipline for the module toggle layer — resolver at `portal/platform/wiki/adapters/modules.py`).

The `WORKSPACES` dict in `portal/platform/inference/router/workspaces.py` is loaded at import time from `portal.yaml` via `portal.platform.inference.config.get_workspace_dict()`, which excludes every workspace whose `module:` is currently disabled (per `portal.platform.wiki.adapters.modules.enabled_modules()`) — the `eval` module additionally honors the `PORTAL_ENABLE_EVAL=1` bench-harness opt-in. The `MCP_SERVERS` dict in `portal/platform/inference/tool_registry.py` is similarly derived from the fleet table via `get_pipeline_mcp_servers()` (not module-gated — MCP servers are independent services per Rule 3; disabling a module hides its workspaces/routing, not its container).

Toggle a module's enabled state with `python3 -m portal.platform.inference.cli module {list,status,enable,disable}` — confirm-gated by default (writes a `proposed` wiki unit under `portal_wiki/proposed/`), pass `--yes` to apply immediately. A confirmed change re-runs `sync-config` automatically.

After any workspace change, verify consistency:
```bash
python3 -m pytest tests/unit/test_generated_artifacts_fresh.py tests/unit/test_mcp_fleet_single_source.py -q
```

Auto-routing uses two layers: **Layer 1** — LLM-based intent classifier (default: `gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M`, ~840ms warm, 82.2% accuracy; switchable via `LLM_ROUTER_MODEL` in `.env`). **Layer 2** — weighted keyword scoring (fallback on confidence < 0.5 or timeout). Vision text-only fallback: `auto-vision` with no image parts reroutes to `auto-reasoning`.
