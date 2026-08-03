---
id: unit-tests-unit-test_capability_lib
kind: mixed
title: "Unit tests \u2014 test_capability_lib"
sources:
- type: code
  path: tests/unit/test_capability_lib.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8922272
updated_at: 1785800468.8922272
---

Unit tests for test_capability_lib.

## Why

The scoring logic is the contract of the capability bench, and its tests verify the extraction and scoring without an LLM. A scorer that mis-extracted the final answer would score a model on its preamble instead of its output, so the deterministic parts are verified separately from any model.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
