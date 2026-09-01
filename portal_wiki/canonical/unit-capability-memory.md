---
id: unit-capability-memory
kind: mixed
title: "Memory MCP — temporal knowledge-graph persistence"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/platform/memory/memory_mcp.py
- type: code
  path: portal/platform/memory/graph_memory.py
- type: code
  path: portal/platform/memory/test_graph_memory.py
- type: code
  path: portal/platform/lance_guard.py
- type: code
  path: config/inference/tools_manifest_memory_mcp.json
claims: []
confidence: high
tags:
- capability
- mcp
- platform
---

# Memory MCP — temporal knowledge-graph persistence

## What

The Memory MCP (port 8920) stores and recalls facts across conversations,
backed by a temporal knowledge graph (`portal/platform/memory/graph_memory.py`).
`memory_mcp.py` is a thin server that registers the graph implementation;
`TASK_MEMORY_GRAPH_OVERHAUL_V1` replaced the previous flat-vector store — the
graph is the memory, not an addition next to it, and the flat top-K recall path
was deleted. It is pipeline- and IDE-exposed.

The graph's LanceDB directory is `PORTAL5_LANCE_DIR` (default
`/Volumes/data01/portal5_lance`, an external volume). `portal/platform/lance_guard.py`
gates `_conn()` on that volume being mounted: writing vectors to an
unmounted-then-remounted path is worse than refusing to start, so
`require_lance_dir` raises `LanceStoreUnavailableError` rather than let
`os.makedirs` create a shadow tree on the boot disk. The RAG stores
(`rag_mcp.py`, `rag_multimodal.py`) share the same guard.

## How it's used

`remember` embeds a memory into the `memory` table AND runs a local model
(`MEMORY_EXTRACT_MODEL`, default `gemma4:e4b-it-q4_K_M`, via
`OLLAMA_CHAT_URL`) to extract entities and relations, populating the
`memory_entities` and `memory_relations` tables on write. `recall` is
graph-aware: it vector-seeds memories and entities from the query, expands
relations up to `hops` deep, and returns the matched memories plus a
`graph_context` of connected nodes and edges — the flat top-K response keys
(`query` / `num_results` / `memories`) are preserved so callers don't break.
`forget` / `list_memories` / `clear_memories` keep their contracts.

New graph tools: `link` (add an explicit edge between two entities),
`neighbors` (entities within N hops of a named entity), `entity_timeline` (the
time-ordered relations observed for an entity — how understanding of it
evolved), and `graph_recall` (an alias for the now-graph-aware `recall`).

## Why it exists

A flat vector store answers "what memory is similar to this" but is blind to
how facts connect and how understanding changed over time. The knowledge graph
makes both first-class: recall follows relations, and every edge is timestamped.
Extraction runs by default — it is the write path, not an opt-in.

## Value

An agent priming context at the start of a session gets not just the top
matching facts but the graph around them, and can ask how its picture of an
entity built up over time.

## Migration

Done live: `graph_memory.migrate_existing()` re-processed every existing
flat-vector memory through extraction and populated the graph tables
(`memory_entities`, `memory_relations`). A pre-migration snapshot of the
LanceDB volume was taken for operational safety; the design is forward, with no
parallel flat path retained. `_norm_entity` / `_norm_relation` make extraction
robust to the shapes local models actually emit (list `["A","rel","B"]` or dict
`{"src":…,"relation":…,"dst":…}` with varying key names), so one malformed
tuple never aborts a migration.

## Reconciliation (TASK_VL_RETRIEVAL_HARDENING_AND_CLOSEOUT_V2 C2)

T8 (`433b56e8`) recorded **73/73 memories migrated, 216 entities, 193
relations** — run *inside* `portal5-mcp-memory` as the container's `portal`
user. That store is the **Docker named volume `portal-5_portal5-lance`**
(mounted at `/app/data/portal5_lance`), not the host path. Queried live it holds
**73 memories, 221 entities, 193 relations** — the +5 entities are ordinary
`remember` growth since T8; nothing was lost.

The apparent "73 → 72, entities/relations never re-counted" gap was a
**store conflation**: `PORTAL5_LANCE_DIR` defaults to
`/Volumes/data01/portal5_lance` on the *host*, a stale pre-T8 orphan (72
memories, no graph tables) that `TASK_VL_RUNTIME_LANDING_V4` P4 "restored" from
`portal5_lance_presnapshot_20260831T233605.tgz` — but that tarball itself only
ever contained the `memory` table at 72 rows. V4's P3 "72 rows, unchanged"
measured the orphan, not the live container store. The host path is inert in
practice (the memory MCP runs only in Docker; host `graph_memory` imports are
test-only with `tmp_path`), so it is left in place, flagged not deleted.

**Completeness check** (both P3 branches): `graph_memory.graph_stats()` returns
`{memories, entities, relations, tables, graph_intact}` where `graph_intact` is
False when `memories > 0` and `entities == 0` — the silent-restore-shortfall
signature. The memory MCP `/health` surfaces it (`status: degraded`,
`graph.intact: false`) so a container health-check catches it at startup, and
`validate_system` check **HB** asserts it over `:8920`.
