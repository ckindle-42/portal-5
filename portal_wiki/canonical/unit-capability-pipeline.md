---
id: unit-capability-pipeline
kind: mixed
title: "Pipeline MCP \u2014 stack introspection and repo explorer"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/platform/mcp_host/pipeline_mcp.py
- type: code
  path: scripts/native-mcp-service.sh
claims: []
confidence: high
tags:
- capability
- mcp
- platform
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Pipeline MCP — stack introspection and repo explorer

## What

The Pipeline MCP (`portal/platform/mcp_host/pipeline_mcp.py`, port 8928) is a
host-native service that introspects the running stack and explores the
repository. It is pipeline- and IDE-exposed and is the tool an agent uses to
decide how to act on Portal itself.

## How it's used

Status and routing tools (`get_pipeline_status`, `list_workspaces`,
`get_loaded_models`, `get_metrics_summary`, `get_workspace_recommendation`)
report live stack state. `trigger_backend_warmup` pre-loads a workspace's
model. The repo tools (`explore_repository`, `list_directory`, `search_files`,
`read_text_file`, `write_file`) operate on the repo tree, with
`explore_repository` running the FastContext explorer subagent.

## Why it exists

Agentic coding on this repo needs two things a persona tool cannot supply: a
trusted view of live pipeline state (which backends are healthy, which models
are warm) and a bounded file surface. Hosting it as an MCP keeps the file
tools scoped to the repo root plus `/tmp`, and the introspection tools read the
same metrics the operator sees — so an agent's plan is grounded in reality.

## Value

A coding session starts by confirming the stack is up, picks a workspace from
the live roster, warms the model, and reads the exact files it will edit —
all through one typed surface. The repo file tools are the same ones this
documentation describes, so the wiki and the agent operate on identical ground
truth.
