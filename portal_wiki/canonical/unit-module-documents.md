---
id: unit-module-documents
kind: mixed
title: "Documents Module \u2014 Word/PowerPoint/Excel/PDF generation and reading"
sources:
- type: code
  path: portal/modules/documents/tools/document_mcp.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
last_generated_commit: 0fec84d46a8898b1b5baf0508af1e25634b099af
claims: []
confidence: high
tags:
- documents
- module
- verified-v1
created_at: 1783821386.790256
updated_at: 1783821386.790256
---

# Documents Module — Word/PowerPoint/Excel/PDF generation and reading

## Tools

`portal.modules.documents.tools.document_mcp` — the document MCP server,
registered as `documents` in `config/portal.yaml` `mcp_fleet:` on port
8913, pipeline- and IDE-exposed.

## Workspaces

- `auto-documents` — document builder workspace
- `auto-extract-uncensored` — uncensored text-extraction lane

## Module State

```yaml
enabled: true
```

## Why

The documents module carries two workspaces on a single tool server, so
its toggle's blast radius is routing plus the `documents` fleet id. The
fenced `enabled:` value is read by `portal/platform/wiki/adapters/modules.py`
(`_unit_enabled_state`) as live config, and the only sanctioned way to
flip it is the confirm-gated CLI write-back (`writeback_module.py`) that
records the change as a `module-state-change:` provenance source. Sourcing
this unit to the adapter, the tool server, and `config/portal.yaml` ties
the prose to the files that actually determine both the toggle and the
surface it controls.
