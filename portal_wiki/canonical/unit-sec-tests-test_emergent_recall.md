---
id: unit-sec-tests-test_emergent_recall
kind: mixed
title: "Security tests \u2014 test_emergent_recall"
sources:
- type: code
  path: portal/modules/security/tests/test_emergent_recall.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.9863338
updated_at: 1785800599.9863338
---

Unit tests for the security module's test_emergent_recall surface.

## Why

Tests detection recall against an arbitrary procedure corpus, proving the coverage JSON generation. The recall measurement is what the emergent loop's gap report is built on.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
