---
id: unit-tests-unit-test_semaphore
kind: mixed
title: "Unit tests \u2014 test_semaphore"
sources:
- type: code
  path: tests/unit/test_semaphore.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892329
updated_at: 1785800468.892329
---

Unit tests for test_semaphore.

## Why

The pipeline's concurrency limits are semaphore-backed, and the tests verify the acquire/release behaviour. A semaphore that did not bound concurrency, or leaked on an error path, would let the pipeline saturate Ollama under load.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
