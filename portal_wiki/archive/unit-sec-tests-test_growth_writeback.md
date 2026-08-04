---
id: unit-sec-tests-test_growth_writeback
kind: mixed
title: "Security tests \u2014 test_growth_writeback"
sources:
- type: code
  path: portal/modules/security/tests/test_growth_writeback.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986346
updated_at: 1785800599.986346
---

Unit tests for the security module's test_growth_writeback surface.

## Why

Tests that proven detections write back as cited units through the growth loop. The write-back with citations is what makes a proven detection discoverable, and the tests pin the path.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
