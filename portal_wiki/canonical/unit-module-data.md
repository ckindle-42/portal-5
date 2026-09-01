---
id: unit-module-data
kind: mixed
title: "Data & Analytics Module — DuckDB conversational analytics"
sources:
- type: code
  path: portal/modules/data/tools/data_mcp.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: config/portal.yaml
claims:
- probe: modules.enabled
  contains: data
confidence: high
tags:
- data
- analytics
- duckdb
- module
- verified-v1
---

# Data & Analytics Module

## Tools

`data_mcp` (:8939) — sandboxed, local-only DuckDB conversational analytics.
`attach_source` reads a CSV / Parquet / JSON / xlsx file under `DATA_MCP_ROOT`
once and materialises it into a session table; `run_sql` runs against a
connection opened with `enable_external_access=false` (DuckDB then refuses any
filesystem read and cannot re-enable access), fronted by a denylist for a
clean error, results row-capped; `profile_table` returns a per-column profile
(type, nulls, distinct, and min/max/mean for numerics); `list_session` shows
the tables/views built up so far. Sessions persist across calls via a session
id -> DuckDB file map so a persona can build up an analysis over a
conversation.

## Workspaces

- `auto-data` — the data-analysis workspace (module `research`; this module
  gates only the `portal-data` fleet id)

## Module State

```yaml
enabled: true
```

## Why

The data personas ran on raw `execute_python` with no structured-data surface
anywhere in the fleet. This module adds a DuckDB SQL/dataframe capability that
is entirely local and sandboxed to a data root — no external network, a pinned
extension posture, no `COPY ... TO` outside the root, and source files are
never mutated. DuckDB is light, so the module is default on.
