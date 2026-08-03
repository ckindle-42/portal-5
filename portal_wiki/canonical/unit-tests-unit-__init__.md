---
id: unit-tests-unit-__init__
kind: mixed
title: Unit tests package root
sources:
- type: code
  path: tests/unit/__init__.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800427.158647
updated_at: 1785800427.158647
---

The unit test tree root, carrying the version string and marking the hermetic suite.

## Why

The namespace exists so the unit tree has a stable import root; the hermetic rule (no network, no live backends) is what the whole suite is built on.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
