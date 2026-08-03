---
id: unit-router-test-context-inject
kind: mixed
title: "Router context-inject tests \u2014 snippet shape + merge contract"
sources:
- type: code
  path: tests/unit/router/test_context_inject.py
  commit: dfa74e2e
last_generated_commit: dfa74e2e
claims: []
confidence: high
tags:
- authored-v1
- tests
- router
created_at: 1785795513.9173272
updated_at: 1785795513.9173272
---

This test file guards `context_inject` — the router's memory/context
injection layer — against shape drift. It pins how tool results and memory
recall payloads are flattened into snippets, how those snippets merge into the
system message, and that injection stays inert unless the feature is opted in.

## Why

The injector consumes heterogeneous tool shapes (`results`, `memories`, bare
`text`) and must fail loudly on an unknown shape rather than silently dropping
context — the `ValueError` on a weird key is the guard against a new tool
shape silently losing its context on the floor. The system-message merge
contract is the other thing worth pinning: context prepends *after* the
existing system content (not replacing it) and, when no system message exists,
injects a new one at position zero — both are behaviours a reordering refactor
could break without failing any obvious test.

## Interfaces

`_extract_snippets` flattens known result shapes to a list of strings and
raises on unknown shapes; `_inject_context_block` merges a header and snippet
list into the messages' system slot; the recall path respects
`_AUTO_MEMORY_ENABLED`. The tests exercise each with monkeypatched flags and
synthetic message bodies.

## Gotchas

The unknown-shape test exists because the flattening logic is a whitelist of
dict keys — a new key added upstream would previously be ignored silently,
and the `pytest.raises(ValueError)` is the regression guard for that.
