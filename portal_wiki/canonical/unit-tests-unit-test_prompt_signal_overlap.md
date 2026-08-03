---
id: unit-tests-unit-test_prompt_signal_overlap
kind: mixed
title: "Unit tests \u2014 test_prompt_signal_overlap"
sources:
- type: code
  path: tests/unit/test_prompt_signal_overlap.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892301
updated_at: 1785800468.892301
---

Unit tests for test_prompt_signal_overlap.

## Why

A signal that appears in two prompt categories makes the category comparison meaningless, and the lint is the guard. The quality signals are tuned per category, so an overlapping signal would score a response against the wrong category's expectations.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
