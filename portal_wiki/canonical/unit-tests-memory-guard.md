---
id: unit-tests-memory-guard
kind: mixed
title: "Tests memory-guard \u2014 monitor re-export shim"
sources:
- type: code
  path: tests/memory_guard.py
  commit: 4900007a
last_generated_commit: 4900007a
claims: []
confidence: high
tags:
- authored-v1
- tests
created_at: 1785798792.54654
updated_at: 1785798792.54654
---

`tests/memory_guard.py` is a re-export shim: the monitoring primitives live
in `portal.platform.inference.router.monitor`, and this module re-exports
them so callers that historically imported from `tests.memory_guard` keep
working.

## Why

The memory monitoring was relocated into the router monitor module, and a
relocation that broke the old import path would break the bench lifecycle
code that drains models. The shim preserves the historical surface while
pointing at the canonical implementation.

## Interfaces

Re-exports the monitor's surface: `memory_pct`, `free_ram_gb`, `purge_memory`,
`restart_ollama`, the wait functions, and the defaults.

## Gotchas

New imports should target the monitor module — the shim is for existing
callers.
