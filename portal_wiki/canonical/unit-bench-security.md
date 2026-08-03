---
id: unit-bench-security
kind: mixed
title: "Bench security \u2014 backward-compat shim to security core"
sources:
- type: code
  path: tests/benchmarks/bench_security.py
  commit: f09fdb85
last_generated_commit: f09fdb85
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798611.415126
updated_at: 1785798611.415126
---

`bench_security.py` is a thin re-export shim: all the security bench
implementation now lives in `portal/modules/security/core`, relocated intact,
and this module preserves the historical import path for backward
compatibility.

## Why

The security bench was relocated into the security module as part of the
modularization, and a relocation that breaks the old import path would break
every script and prompt that references it. The shim re-exports the core
surface (config, prompts, scoring, exec sequences, and `main`) so existing
callers keep working while new code imports from the canonical location. It
is the same backward-compat pattern as `router_pipe`.

## Interfaces

Re-exports the security bench's public surface from
`portal.modules.security.core`, including `main`, `BenchConfig`, the
scoring functions, and the exec sequences.

## Gotchas

New code should import from the canonical core location — the shim is for
existing callers, not a second home for the bench.
