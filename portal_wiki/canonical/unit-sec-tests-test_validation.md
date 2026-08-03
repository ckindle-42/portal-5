---
id: unit-sec-tests-test_validation
kind: mixed
title: "Security tests \u2014 test_validation"
sources:
- type: code
  path: portal/modules/security/tests/test_validation.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.563254
updated_at: 1785800626.563254
---

Unit tests for the security module's test_validation surface.

## Why

The validation loop's pass/fail semantics are pinned without a live loop. A validation that passed a use-case without the twin-control gate would certify a detection with false positives, so the semantics are verified.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
