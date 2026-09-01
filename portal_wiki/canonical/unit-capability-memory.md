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

The existing flat-vector memories are migrated into the graph in-task
(`graph_memory.migrate_existing()` re-processes every memory through
extraction). A pre-migration snapshot of `PORTAL5_LANCE_DIR` is taken for
operational safety; the design is forward, with no parallel flat path retained.
