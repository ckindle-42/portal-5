---
id: unit-tests-unit-test_model_catalog_parity
kind: mixed
title: Model catalog parity tests
sources:
- type: code
  path: tests/unit/test_model_catalog_parity.py
  commit: d5234798
last_generated_commit: e4e79f1d894d33cf7c3dfb9340dde71bd401a6cb
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800427.158732
updated_at: 1785800427.158732
---

Tests that backends.yaml model ids map one-to-one with the MODEL_CATALOG doc sections.

## Why

A model id that diverges between the catalog and the doc is a drift nobody notices until a workflow references the wrong one; the parity test is the guard.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
