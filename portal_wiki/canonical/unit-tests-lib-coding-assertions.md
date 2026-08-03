---
id: unit-tests-lib-coding-assertions
kind: mixed
title: "Tests lib coding assertions \u2014 structural artifact checks"
sources:
- type: code
  path: tests/lib/coding_assertions.py
  commit: f2f2516d
last_generated_commit: f2f2516d
claims: []
confidence: high
tags:
- authored-v1
- tests
- lib
created_at: 1785798259.9462762
updated_at: 1785798259.9462762
---

`coding_assertions.py` holds the behavioral assertions for coding-persona
responses, mirroring the compliance assertions: the same `AssertionResult` /
`ScenarioOutcome` types and the same MUST/SHOULD/INFO severities, dispatched
by spec name from the matrix driver.

## Why

The assertion philosophy is explicit: test that the response delivers a
*runnable, complete* code artifact matching the persona's mandated output
shape, while avoiding coupling to specific algorithmic choices that constrain
the model unnecessarily. So the assertions check for absence of placeholders,
presence of required structural elements (a fenced code block, no premature
truncation), and discipline around user-stated constraints — not "uses
requestAnimationFrame". Testing structure over algorithm is what keeps the
coding matrix stable across model versions that solve the same task
differently.

## Interfaces

The assertion functions take a response and return an `AssertionResult`; the
severity types (MUST/SHOULD/INFO) let the harness weight a failure
appropriately.

## Gotchas

A response with no fenced code block is structurally incomplete even if the
prose explains the approach — the structural assertions are what catch a
model that describes code without delivering it.
