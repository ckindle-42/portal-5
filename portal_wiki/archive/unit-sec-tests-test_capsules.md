---
id: unit-sec-tests-test_capsules
kind: mixed
title: "Security tests \u2014 test_capsules"
sources:
- type: code
  path: portal/modules/security/tests/test_capsules.py
  commit: 862c7b11
last_generated_commit: 862c7b11
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986312
updated_at: 1785800599.986312
---

Unit tests for the security module's test_capsules surface.

## Why

Unit tests for the proof capsules: the integrity-hashed replayable finding receipts. A capsule that could not be replayed or verified would not prove the finding, so the integrity contract is pinned.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
