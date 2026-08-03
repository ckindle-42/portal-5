---
id: unit-tests-lib-init
kind: mixed
title: "Tests lib \u2014 shared acceptance/matrix test library"
sources:
- type: code
  path: tests/lib/__init__.py
  commit: f2f2516d
last_generated_commit: f2f2516d
claims: []
confidence: high
tags:
- authored-v1
- tests
- lib
created_at: 1785798244.6095161
updated_at: 1785798244.6095161
---

The tests/lib package is the shared test library for the acceptance and
matrix harnesses: coding and compliance assertion functions and fixtures,
the result model, and the streaming-wait helper. Every module is pure Python
with no Docker or network dependencies, so the whole library unit-tests
without a live backend.

## Why

The acceptance and persona-matrix harnesses need the same assertion and
result plumbing, and duplicating it per harness is how two harnesses start
scoring the same scenario differently. The package centralises the shared
pieces — assertion functions with their MUST/SHOULD/INFO severities, fixture
loaders, the result model, and the stream waiter — so a scoring change
applies everywhere it is used, and the no-Docker/no-network rule keeps the
library testable in CI on a bare clone.

## Interfaces

`compliance_assertions`/`coding_assertions` are the pure assertion
functions; `compliance_fixtures`/`coding_fixtures` load and parameterize the
scenario YAML; `results` is the result model; `stream_wait` is the
event-driven streaming waiter.

## Gotchas

The fixtures are the single source of truth — the loaders are purely a
transform over the YAML, so a scenario lives in the fixture file, not in
Python.
