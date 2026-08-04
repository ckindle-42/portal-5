---
id: unit-tests-unit-test_adhoc_probe
kind: mixed
title: "Unit tests \u2014 test_adhoc_probe"
sources:
- type: code
  path: tests/unit/test_adhoc_probe.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8922062
updated_at: 1785800468.8922062
---

Unit tests for test_adhoc_probe.

## Why

The probe is the pre-registration TPS tool an operator runs to sanity-check a candidate before wiring it into the fleet, and its unit tests prove the measurement and fallback logic without a live backend. A probe that mis-measured TPS would send the wrong candidates into the bench, so the measurement logic is pinned hermetically before any real run.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
