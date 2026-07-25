---
id: unit-mcp-dev-tooling-tools
kind: what
title: "MCP_DEV_TOOLING \u2014 Tools"
sources:
- type: doc
  path: docs/MCP_DEV_TOOLING.md
  commit: 05e42ec2
  section: Tools
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.571975
updated_at: 1784946220.571975
---

| Tool | What it does |
|---|---|
| `get_pipeline_status` | Pipeline health, workspace count, version |
| `list_workspaces` | All workspaces (currently 104) with names/descriptions; accepts optional filter string |
| `get_loaded_models` | Which Ollama models are in VRAM, their sizes, expiry times |
| `get_metrics_summary` | Request totals, tool call counts, error rates, TPS from Prometheus |
| `get_workspace_recommendation` | Given a task description, returns the best workspace ID with reasoning |
| `trigger_backend_warmup` | Pre-loads a workspace model into VRAM before a long session |
| `explore_repository` | **FastContext subagent** — finds relevant files and line ranges |

> **Two consumer paths.** These tools are reachable two ways:
> (A) **opencode / Claude Code** connect to `:8928` directly over MCP streamable-http
> (via `.mcp.json`); (B) the **in-pipeline `auto-coding` workspace (`?variant=laguna`)** reaches them
> through the pipeline's ToolRegistry, which discovers `GET :8928/tools` and dispatches
> `POST :8928/tools/{name}`. Both paths are served by the same `_impl_*` helpers in
> `pipeline_mcp.py`, so behavior is identical. `:8928` is registered in
> `MCP_SERVERS["pipeline"]` (`MCP_PIPELINE_URL` to override).
