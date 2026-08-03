---
id: unit-sec-tests-test_labexec_coverage
kind: mixed
title: "Security tests \u2014 test_labexec_coverage"
sources:
- type: code
  path: portal/modules/security/tests/test_labexec_coverage.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986356
updated_at: 1785800599.986356
---

Unit tests for the security module's test_labexec_coverage surface.

## Why

Unit tests for lab-exec coverage, dry-run and synthetic with no live lab or Docker. The coverage measurement must be verifiable without the lab, so it is exercised synthetically.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
