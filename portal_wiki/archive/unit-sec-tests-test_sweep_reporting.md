---
id: unit-sec-tests-test_sweep_reporting
kind: mixed
title: "Security tests \u2014 test_sweep_reporting"
sources:
- type: code
  path: portal/modules/security/tests/test_sweep_reporting.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.5632482
updated_at: 1785800626.5632482
---

Unit tests for the security module's test_sweep_reporting surface.

## Why

Reporting a single winner when the arms overlap would misstate the comparison. The sweep reporting tests pin the arm-versus-arm deltas so the report reflects the actual comparison rather than a misleading single winner.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
