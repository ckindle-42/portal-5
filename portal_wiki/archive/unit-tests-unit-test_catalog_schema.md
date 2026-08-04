---
id: unit-tests-unit-test_catalog_schema
kind: mixed
title: "Unit tests \u2014 test_catalog_schema"
sources:
- type: code
  path: tests/unit/test_catalog_schema.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.892232
updated_at: 1785800468.892232
---

Unit tests for test_catalog_schema.

## Why

A persona referencing a missing parent is a catalog corruption that would break the persona's tool and workspace resolution at runtime, and the schema tests are what catch it at load time. Catching it at load is cheaper than discovering it when a persona silently fails to resolve.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
