---
id: unit-capability-data
kind: mixed
title: "Data MCP — sandboxed DuckDB conversational analytics"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/data/tools/data_mcp.py
- type: code
  path: portal/modules/data/tests/test_data_mcp.py
- type: code
  path: scripts/native-mcp-service.sh
claims:
- probe: modules.enabled
  contains: data
confidence: high
tags:
- capability
- mcp
- data
- analytics
---

# Data MCP — sandboxed DuckDB conversational analytics

## What

The Data MCP (`portal/modules/data/tools/data_mcp.py`, port 8939) is a
read-first, local-only analytics server, pipeline- and IDE-exposed, backing
the `auto-data` workspace. It is host-native (stdlib + lazy `duckdb` / pandas).

## How it's used

`attach_source` reads a tabular file (`DATA_MCP_ROOT`-confined, default
`~/AI_Output`) exactly once through a short-lived loader connection and
materialises it into a session table; `run_sql` queries the session on a
cached connection opened with `enable_external_access=false`, so it can never
open an arbitrary path or re-enable filesystem access (a denylist on
`read_csv` / `read_parquet` / `read_json` / `read_blob` / `glob` / `SET` /
`ATTACH` / `COPY` / `INSTALL` sits in front for a clean error). Rows are
capped at `DATA_MCP_MAX_ROWS`. `profile_table` gives a per-column profile;
`list_session` enumerates the session's tables. Each `session_id` maps to its
own DuckDB file under `DATA_MCP_SESSIONS`, so an analysis accumulates across a
conversation — scratch tables live in the session DB, never in the source
files.

## Why it exists

Ten data personas (Data Analyst, Data Scientist, Database Architect,
Statistician, ML Engineer, ...) ran on raw `execute_python` with no structured
SQL / dataframe surface anywhere in the fleet. This is the DuckDB-backed
capability — attach, query, profile, persist — entirely local, no external
network, and one-of-a-kind for a self-hosted Apple-Silicon stack.

## Value

An analyst gets real SQL over a CSV or Parquet file with a durable session
instead of re-parsing the file in Python on every turn, and the sandbox
guarantees a query cannot reach outside the data root or mutate a source.
