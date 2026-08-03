---
id: unit-tests-lib-coding-fixtures
kind: mixed
title: "Tests lib coding fixtures \u2014 scenario loader/parameterizer"
sources:
- type: code
  path: tests/lib/coding_fixtures.py
  commit: f2f2516d
last_generated_commit: f2f2516d
claims: []
confidence: high
tags:
- authored-v1
- tests
- lib
created_at: 1785798265.901275
updated_at: 1785798265.901275
---

`coding_fixtures.py` loads `tests/fixtures/coding_scenarios.yaml` and
parameterizes it, mirroring the compliance fixtures: the same
`ConcreteScenario` type and the same `expand_scenarios()` / `run_assertions()`
interface, so the matrix driver consumes both identically.

## Why

The scenario YAML is the single source of truth for what a coding persona is
asked to do, and the loader is purely a transform over it. Mirroring the
compliance fixture interface is what lets the matrix driver treat coding and
compliance scenarios uniformly — the dispatch table knows coding-specific
assertion families (language.X, constraint.X) while the iteration shape stays
identical.

## Interfaces

`expand_scenarios()` produces the concrete scenario tuples and
`run_assertions()` dispatches to the coding-specific assertions.

## Gotchas

A scenario that names a language the dispatch table does not know is silently
underexercised — the dispatch table and the fixture vocabulary must stay in
sync.
