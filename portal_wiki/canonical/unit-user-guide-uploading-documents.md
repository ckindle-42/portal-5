---
id: unit-user-guide-uploading-documents
kind: what
title: "USER_GUIDE \u2014 Uploading Documents"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: portal/modules/research/tools/rag_mcp.py
last_generated_commit: 9623f6b25b3e922bd0cf4b3885a926a4728b26a1
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.515612
updated_at: 1784946220.515612
---

Open the chat interface at the Open WebUI address (bound to `127.0.0.1:8080` by
default in the compose manifest), click the paperclip to attach a file, and
upload one of the supported formats. The attachment is automatically chunked per
`CHUNK_SIZE`/`CHUNK_OVERLAP`, embedded with the Harrier model on port 8917, and
indexed so the chat can ground answers in it. For a persistent library, create a
knowledge collection from the workspace knowledge panel and upload documents
there; the pipeline's RAG server stores them in LanceDB, and you can reference
the collection from any chat with a `#` marker.

## Why

Uploading is two different mechanisms that the guide blurred into one flow:
ad-hoc chat attachments handled by Open WebUI with repository-controlled chunk
and embedding settings, versus persistent knowledge collections owned by the RAG
MCP server. Grounding both halves to the compose manifest and `rag_mcp.py` makes
the distinction explicit and keeps the unit accurate if either path changes.
