---
id: unit-inference-config
kind: mixed
title: "Inference config \u2014 Pydantic portal.yaml model layer"
sources:
- type: code
  path: portal/platform/inference/config.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
created_at: 1785797748.6843362
updated_at: 1785797748.6843362
---

The inference config module is the Pydantic model layer over
`config/portal.yaml`: it defines every shape (workspace, persona, MCP server,
model, chain hop, council spec, tool-preselect spec) and the loader that
parses the file into them, plus the accessors the router and the fleet need.

## Why

The config models are the single typed view of the portal config — the thing
that turns a YAML file into objects every other module can use without
re-parsing. The accessors (`get_workspace_dict`, `get_pipeline_mcp_servers`,
`load_persona_map`) are the functions the workspace dict, the tool registry,
and the MCP fleet all build on, and the `_eval_enabled` gate is how the bench
harness opts in to the eval module's workspaces. The persona model also loads
prompt templates from the shared persona-matrix prompt bodies, so a persona
can reference a template by name rather than embedding it.

## Interfaces

`PortalConfig` is the root model; `load_portal_config` parses the file;
`get_workspace_dict` returns the live workspace map (excluding disabled
modules); `get_pipeline_mcp_servers` returns the pipeline-facing fleet table;
`load_persona_map` returns the persona model with resolved templates;
`ollama_url` is the backend URL helper.

## Gotchas

The module-level workspace exclusion honors the module toggles — a workspace
whose module is disabled does not appear in `get_workspace_dict`, which is
how a toggled module hides its routing.
