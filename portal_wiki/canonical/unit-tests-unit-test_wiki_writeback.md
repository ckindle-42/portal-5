---
id: unit-tests-unit-test_wiki_writeback
kind: mixed
title: "Unit tests \u2014 test_wiki_writeback"
sources:
- type: code
  path: tests/unit/test_wiki_writeback.py
  commit: 3e884375
last_generated_commit: 3e884375
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785800468.8923662
updated_at: 1785800468.8923662
---

Unit tests for test_wiki_writeback.

## Why

The write-back propose/confirm path is the growth loop's bridge into canonical, and its tests pin the provenance. A write-back that dropped provenance would make a machine-generated unit enter canonical without the citations that make it trustworthy.

## Interfaces

The suite exercises its target hermetically (mocked HTTP and subprocesses, no live backends) and reports pass/fail per test.

## Gotchas

As a unit test it must run with no network and no live services — a test that reaches a real backend violates the hermetic contract and fails in CI.
