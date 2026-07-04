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
created_at: 1783195000.807789
updated_at: 1783195000.807789
---

python3 -m portal_pipeline.sync_config
```

`sync-config` is idempotent — running it twice produces no diff. The test suite (`tests/unit/test_generated_artifacts_fresh.py`) verifies this.

The `WORKSPACES` dict in `portal_pipeline/router/workspaces.py` is loaded at import time from `portal.yaml` via `portal_pipeline.config.get_workspace_dict()`. The `MCP_SERVERS` dict in `portal_pipeline/tool_registry.py` is similarly derived from the fleet table via `get_pipeline_mcp_servers()`.

After any workspace change, verify consistency:
```bash
python3 -m pytest tests/unit/test_generated_artifacts_fresh.py tests/unit/test_mcp_fleet_single_source.py -q
```

Auto-routing uses two layers: **Layer 1** — LLM-based intent classifier (default: `gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M`, ~840ms warm, 82.2% accuracy; switchable via `LLM_ROUTER_MODEL` in `.env`). **Layer 2** — weighted keyword scoring (fallback on confidence < 0.5 or timeout). Vision text-only fallback: `auto-vision` with no image parts reroutes to `auto-reasoning`.
