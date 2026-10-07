---
id: unit-user-guide-cross-session-memory
kind: what
title: "USER_GUIDE \u2014 Cross-Session Memory"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: portal/platform/memory/memory_mcp.py
- type: code
  path: portal/platform/inference/router/context_inject.py
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.516544
updated_at: 1784946220.516544
---

Portal 5 keeps a persistent memory of facts you share across conversations.
`ENABLE_MEMORY_FEATURE=true` turns on Open WebUI's native memory store, and the
pipeline's `remember`/`recall` tools let workspaces such as `auto-daily`
(explicitly flagged `inject_memory` and `memory_writeback`) both read and write
that store. Memories are embedded and indexed locally by the host-native embedder on port 8917
(MLX Qwen3-Embedding-0.6B) and persisted in the memory MCP's graph store. In the Open WebUI interface you can view or edit stored memories
under Settings → Personalization → Memory.

Operators can inspect graph-extraction failures through the Memory MCP's
Prometheus endpoint at `/metrics`.

## Why

The guide's account of memory was a description of a UI surface; the feature's
existence and its indexer are decided by repository configuration. Grounding here
anchors the claim to `ENABLE_MEMORY_FEATURE` and `MEMORY_EMBEDDING_MODEL`, so a
future change to either flag cannot silently invalidate this unit's statement
about how memories are stored and retrieved across sessions.
