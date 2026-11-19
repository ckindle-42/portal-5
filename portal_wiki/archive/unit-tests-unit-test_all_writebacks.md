---
id: unit-tests-unit-test_all_writebacks
historical: true
kind: mixed
title: "Unit tests \u2014 test_all_writebacks"
sources:
- type: code
  path: tests/unit/test_all_writebacks.py
  commit: d5234798
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit

---

Unit tests for test_all_writebacks.

## Why

The write-backs are the growth loop's bridge into the wiki, and their tests pin the propose/confirm contract across all three loops at once. If one loop's write-back dropped provenance or bypassed the confirm gate, the finding would enter canonical without its evidence trail, so all three are tested together.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
