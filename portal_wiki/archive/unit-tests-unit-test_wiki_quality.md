---
id: unit-tests-unit-test_wiki_quality
historical: true
kind: mixed
title: "Unit tests \u2014 test_wiki_quality"
sources:
- type: code
  path: tests/unit/test_wiki_quality.py
  commit: d5234798
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit

---

Unit tests for test_wiki_quality.

## Why

The gate is the definition of coverage, so its tests pin both directions: no false rejections and every fake caught. A gate that failed either direction would make the coverage number meaningless, so both are asserted.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
