---
id: unit-tests-unit-test_mcp_fleet_single_source
kind: mixed
title: "Unit tests \u2014 test_mcp_fleet_single_source"
sources:
- type: code
  path: tests/unit/test_mcp_fleet_single_source.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892273
updated_at: 1785800468.892273
---

Unit tests for test_mcp_fleet_single_source.

## Why

A fleet id or port that appears in two places is a collision waiting to happen, and the single-source test is the guard. Two servers on one port, or one id declared twice, would fail nondeterministically at runtime, so the single-source property is asserted.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
