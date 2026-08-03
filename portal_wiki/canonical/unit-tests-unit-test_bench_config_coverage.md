---
id: unit-tests-unit-test_bench_config_coverage
kind: mixed
title: Bench config coverage guard
sources:
- type: code
  path: tests/unit/test_bench_config_coverage.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800427.1586728
updated_at: 1785800427.1586728
---

Guard test that the bench harness config dicts stay in sync with the live workspaces.

## Why

A bench config that names a workspace the live catalog does not have would silently skip it; the guard is what catches the drift at the config level.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
