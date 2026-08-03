---
id: unit-scripts-embedding-server
kind: mixed
title: "Script \u2014 embedding-server"
sources:
- type: code
  path: scripts/embedding-server.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799479.97363
updated_at: 1785799479.97363
---

Serves an OpenAI-compatible embeddings endpoint using sentence-transformers, replacing the TEI Docker service on Apple Silicon where the x86-only TEI image has no ARM64 manifest.

## Why

The embedding tier must run on Apple Silicon, and the TEI image is x86-only with no ARM64 manifest — so a native sentence-transformers server is the replacement that provides the same embeddings API on this hardware. Serving the OpenAI-compatible shape is what lets the memory and RAG servers consume it without a client change.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
