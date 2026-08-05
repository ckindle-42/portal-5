---
id: unit-mcp-dev-tooling-tools
kind: what
title: "MCP_DEV_TOOLING \u2014 Tools"
sources:
- type: code
  path: portal/platform/mcp_host/pipeline_mcp.py
- type: code
  path: portal/platform/inference/tool_registry.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.571975
updated_at: 1784946220.571975
---

The pipeline MCP exposes introspection and repository tools, all implemented as
`_impl_*` helpers in `portal/platform/mcp_host/pipeline_mcp.py`. `get_pipeline_status`
reports pipeline health, `list_workspaces` lists the model catalog with an optional
filter, `get_loaded_models` reads Ollama's loaded set, `get_metrics_summary` folds
the /metrics text into a summary, `get_workspace_recommendation` maps a task
description to a workspace, `trigger_backend_warmup` pre-loads one, and
`explore_repository` runs the FastContext subagent. File tools `read_text_file`,
`write_file`, `list_directory`, and `search_files` operate on the repo tree with
explicit allow-roots. The tools are reachable two ways: directly over MCP
streamable-HTTP from the IDE, or through the pipeline ToolRegistry, which discovers
them via GET /tools and dispatches POST /tools/{name} using the `pipeline` entry in
`MCP_SERVERS` (`MCP_PIPELINE_URL` overrides the base URL).

## Why

Two consumer paths exist because the same tools serve both an IDE and the in-pipeline
agentic workspaces, and sharing the `_impl_*` helpers guarantees identical behaviour
from both. That single-source-of-truth design is what keeps the tool contract from
diverging between a Claude Code session and a workspace tool call.
