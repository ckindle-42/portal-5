---
id: unit-tests-unit-test_routing
kind: mixed
title: "Unit tests \u2014 test_routing"
sources:
- type: code
  path: tests/unit/test_routing.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892323
updated_at: 1785800468.892323
---

Unit tests for test_routing.

## Why

The intent router is the Layer-1 classifier, and its tests verify the classification and fallback without a live model. A router regression would send requests to the wrong workspace silently, so the classification and the keyword fallback are both pinned.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
