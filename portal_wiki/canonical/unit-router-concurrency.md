---
id: unit-router-concurrency
kind: mixed
title: "Router concurrency \u2014 three-tier semaphores + RequestSlot"
sources:
- type: code
  path: portal/platform/inference/router/concurrency.py
  commit: a234187e
last_generated_commit: a234187e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798058.258883
updated_at: 1785798058.258883
---

`concurrency.py` owns the request-concurrency machinery: the three
semaphores (global request, per-workspace, per-API-key) and `RequestSlot`,
which provides single-owner lifecycle for all three within one request.

## Why

The concurrency layer exists because the pipeline must bound how many
requests hit Ollama simultaneously — an unbounded flood would evict models
and degrade every request. The three-tier semaphore design (global, per
workspace, per key) is the answer to three different exhaustion modes:
overall load, one workspace saturating the backend, and one API key
monopolising the pipeline. `RequestSlot` was extracted because the same
acquire/release lifecycle was previously split across five release sites in
the monolith — a request that forgot to release a semaphore on one error path
would leak it permanently, and the single-owner slot makes that impossible.

## Interfaces

The module exposes the semaphore singletons, the limit helpers
(`_api_key_limit`, `_get_workspace_concurrency_limit`), and `RequestSlot`
with its acquire/release lifecycle.

## Gotchas

The semaphores are mutable process singletons — with multiple uvicorn
workers, each process has its own set, so the concurrency limits are
per-process, not fleet-wide.
