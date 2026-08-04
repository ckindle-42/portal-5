---
id: unit-tests-unit-test_wiki_core
kind: mixed
title: "Unit tests \u2014 test_wiki_core"
sources:
- type: code
  path: tests/unit/test_wiki_core.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892361
updated_at: 1785800468.892361
---

Unit tests for test_wiki_core.

## Why

The wiki core is the data model everything else compiles against, and its tests pin the schema and store contract. A schema regression would break every unit load and save, so the core contract is pinned first.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
