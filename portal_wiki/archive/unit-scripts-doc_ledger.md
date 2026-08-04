---
id: unit-scripts-doc_ledger
kind: mixed
title: "Script \u2014 doc_ledger"
sources:
- type: code
  path: scripts/doc_ledger.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799476.296475
updated_at: 1785799476.296475
---

Binds each documentation file to the source paths that determine its correctness and records the commit each doc was last reconciled against; a doc is stale when any bound source path changed since.

## Why

The ledger implements the doc-currency signal: a doc bound to its determining sources can be mechanically checked for staleness against the last-reconciled commit. It is the honest abstraction AK reports — when no docs are bound, the ledger is empty and reports SKIP rather than a false green.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
