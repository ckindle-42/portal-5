---
id: unit-tests-unit-test_wiki_quality
kind: mixed
title: "Unit tests \u2014 test_wiki_quality"
sources:
- type: code
  path: tests/unit/test_wiki_quality.py
  commit: 3e884375
last_generated_commit: 6afb262648d307376dfb4f839eeed69c02112d04
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8923619
updated_at: 1785800468.8923619
---

Unit tests for test_wiki_quality.

## Why

The gate is the definition of coverage, so its tests pin both directions: no false rejections and every fake caught. A gate that failed either direction would make the coverage number meaningless, so both are asserted.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
