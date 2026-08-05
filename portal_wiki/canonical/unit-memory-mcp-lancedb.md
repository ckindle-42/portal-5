---
id: unit-memory-mcp-lancedb
kind: mixed
title: "Memory MCP \u2014 cross-conversation LanceDB recall"
sources:
- type: code
  path: portal/platform/memory/memory_mcp.py
  commit: b0aa6770
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- authored-v1
- mcp
- memory
created_at: 1785795062.696089
updated_at: 1785795062.696089
---

The memory MCP gives the platform a cross-conversation persistent store,
backed by LanceDB and served over the fleet's HTTP shape. It is the one
service a persona reaches for facts that must survive a chat: user
preferences, stable project context, and conclusions worth carrying forward.
Recall is hybrid — vector similarity against the embedding service, a recency
boost that decays over ninety days, and optional tag or category filters —
rather than a bare top-K search.

## Why

The pipeline is deliberately stateless (conversation history lives in Open
WebUI), so anything a persona wants to remember across sessions has to be
written somewhere the next chat can read. That somewhere is this server, and
its hybrid recall is the design answer to a plain vector search's blind spot:
a memory from yesterday about the current project should outrank an equally
similar memory from three months ago, which is exactly the recency term in
the score. The `text` field is also constrained to be self-contained — no
pronouns pointing at the current chat — because a memory is useless to a
future conversation if it only makes sense in the one that wrote it.

## Interfaces

`remember` stores a self-contained sentence with a category and tags.
`recall` embeds the query, searches with the recency-adjusted score, and
returns the top matches. `forget` deletes by id, `list_memories` inventories
with optional filters, and `clear_memories` is the admin bulk delete gated on
a `YES_DELETE_ALL` token. Embeddings come from the local MLX embedding
service (`MLX_EMBEDDING_URL`), so no text ever leaves the machine to be
vectorised.

## Gotchas

`_get_table` lazily creates the LanceDB table with a fixed 1024-dimension
vector schema on first use — if the embedding service's output dimension ever
changes, existing tables must be migrated, not just reopened. Recall fetches
`top_k * 3` candidates before the recency re-rank so the boost does not lose
a genuinely similar older hit to a merely-recent one.
