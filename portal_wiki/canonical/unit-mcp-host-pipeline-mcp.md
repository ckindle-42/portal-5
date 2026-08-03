---
id: unit-mcp-host-pipeline-mcp
kind: mixed
title: "Pipeline MCP \u2014 coding-tool stack introspection (zero inference imports)"
sources:
- type: code
  path: portal/platform/mcp_host/pipeline_mcp.py
  commit: ee7ca08a
last_generated_commit: ee7ca08a
claims: []
confidence: high
tags:
- authored-v1
- mcp
- platform
- dev-tooling
created_at: 1785795764.0585442
updated_at: 1785795764.0585442
---

The pipeline MCP gives Claude Code and opencode live introspection of the
Portal 5 stack from inside the repo: workspace catalog, backend health, loaded
models, request metrics, and the FastContext-4B repository explorer. It is
registered in `.mcp.json` so both coding tools pick it up automatically. Its
architectural constraint is that it holds *zero imports* from
`portal/platform/inference/` — everything it reports, it reads by calling the
pipeline's own HTTP endpoints.

## Why

The zero-import rule is what lets this server sit on the MCP side of the
independence boundary: the pipeline exposes its state over HTTP, and this
server consumes that API rather than importing the pipeline's internals. That
keeps the coding tools from dragging the whole inference tier into their
process, and it means the introspection surface cannot drift into calling
private functions — if an endpoint is missing, the server says so instead of
reaching around. The `explore_repository` tool is the notable exception to
"read the HTTP API": it runs a small local model (`FastContext-4B`) with a
READ/GLOB/GREP tool loop to locate code, because a repository walk cannot be
served by the pipeline's chat endpoints.

## Interfaces

`get_pipeline_status`, `list_workspaces`, `get_loaded_models`,
`get_metrics_summary`, `get_workspace_recommendation`, `explore_repository`,
and `trigger_backend_warmup` are the MCP tools. `_resolve_path` plus
`_check_read_allowed` bound the file reads the explorer can issue, and
`_pipeline_headers` carries the API key on every upstream call.

## Gotchas

The server is host-native (port 8928) and reads `PIPELINE_MCP_REPO_ROOT` to
know where the repository lives — a path-based repo access tool is only as
safe as its read-allowlist, which is why the explorer's file reads go through
the resolution-and-check pair rather than raw path use.
