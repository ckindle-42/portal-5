---
id: unit-tests-unit-test_wiki_seed_security
historical: true
kind: mixed
title: "Unit tests \u2014 test_wiki_seed_security"
sources:
- type: code
  path: tests/unit/test_wiki_seed_security.py
  commit: d5234798
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit

---

Unit tests for test_wiki_seed_security.

## Why

The technique-signature seeding turns the SPL library into discoverable units, and the tests verify the seeding. A signature unit that cited the wrong source or missed a technique would make a detection undiscoverable by the agents that query the spine.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
