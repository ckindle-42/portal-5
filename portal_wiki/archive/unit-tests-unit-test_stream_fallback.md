---
id: unit-tests-unit-test_stream_fallback
kind: mixed
title: "Unit tests \u2014 test_stream_fallback"
sources:
- type: code
  path: tests/unit/test_stream_fallback.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8923368
updated_at: 1785800468.8923368
---

Unit tests for test_stream_fallback.

## Why

The SSE stream parsing is where the pipeline's streaming contract lives, and the golden-output tests pin the exact frames. A stream frame that drifted from the expected shape would break every client consuming the SSE output.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
