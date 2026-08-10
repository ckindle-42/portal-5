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
last_generated_commit: 9c0a4efa9fea8836ee3466b206c01b042c59455f
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
that store. Memories are embedded and indexed locally with the Harrier model
(`MEMORY_EMBEDDING_MODEL`), the same indexer the RAG pipeline uses, and persisted
in LanceDB. In the Open WebUI interface you can view or edit stored memories
under Settings → Personalization → Memory.

## Why

The guide's account of memory was a description of a UI surface; the feature's
existence and its indexer are decided by repository configuration. Grounding here
anchors the claim to `ENABLE_MEMORY_FEATURE` and `MEMORY_EMBEDDING_MODEL`, so a
future change to either flag cannot silently invalidate this unit's statement
about how memories are stored and retrieved across sessions.
