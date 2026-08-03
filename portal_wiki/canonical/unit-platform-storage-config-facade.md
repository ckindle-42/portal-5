---
id: unit-platform-storage-config-facade
kind: mixed
title: "Platform storage \u2014 config loader facade"
sources:
- type: code
  path: portal/platform/storage/__init__.py
  commit: b0aa6770
last_generated_commit: b0aa6770
claims: []
confidence: high
tags:
- authored-v1
- platform
- config
created_at: 1785795034.737101
updated_at: 1785795034.737101
---

The platform storage package is the stable re-export boundary over Portal's
config loader. The loader itself lives with the inference pipeline that
consumes it most directly (`portal.platform.inference.config`); this facade
gives other code config access without depending on the whole inference
package.

## Why

Code outside the inference tier — a module, an MCP server, a maintenance
script — legitimately needs the workspace dict, the MCP server table, or the
persona map, but importing `portal.platform.inference` from those places drags
in the full pipeline and violates the independence boundary. The facade is the
pattern's answer: the loader stays where its heaviest consumer is, and
everything else imports the narrow re-export. This is the same shape as the
security module's knowledge boundary, applied to config.

## Interfaces

`load_portal_config`, `PortalConfig`, `get_workspace_dict`,
`get_pipeline_mcp_servers`, `load_persona_map`, and `ollama_url` are
re-exported from `portal.platform.inference.config` through `__all__`, giving
callers a single import point for the config surface.
