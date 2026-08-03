---
id: unit-tests-unit-test_config_schema
kind: mixed
title: "Unit tests \u2014 test_config_schema"
sources:
- type: code
  path: tests/unit/test_config_schema.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.89225
updated_at: 1785800468.89225
---

Unit tests for test_config_schema.

## Why

The config schema is the typed gate over portal.yaml, and its tests verify that malformed shapes are rejected rather than silently accepted. A config that passed schema validation but was structurally wrong would corrupt every derived artifact downstream.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
