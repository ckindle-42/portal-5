---
id: unit-tests-unit-test_media_admission
historical: true
kind: mixed
title: "Unit tests \u2014 test_media_admission"
sources:
- type: code
  path: tests/unit/test_media_admission.py
  commit: d5234798
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit

---

Unit tests for test_media_admission.

## Why

The admission check prevents a media request from loading a model that would evict the other engine's resident model, and the tests pin the check. An admission check that let a second engine load would evict the first mid-generation, corrupting the result.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
