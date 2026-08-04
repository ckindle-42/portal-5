---
id: unit-sec-tests-test_self_index
kind: mixed
title: "Security tests \u2014 test_self_index"
sources:
- type: code
  path: portal/modules/security/tests/test_self_index.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.9864058
updated_at: 1785800599.9864058
---

Unit tests for the security module's test_self_index surface.

## Why

Unit tests for the self-legibility index: read-only enforcement and deterministic ranking. An index that mutated the tree it indexes, or ranked nondeterministically, could not be trusted.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
