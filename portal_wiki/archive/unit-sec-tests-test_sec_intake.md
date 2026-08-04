---
id: unit-sec-tests-test_sec_intake
kind: mixed
title: "Security tests \u2014 test_sec_intake"
sources:
- type: code
  path: portal/modules/security/tests/test_sec_intake.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986401
updated_at: 1785800599.986401
---

Unit tests for the security module's test_sec_intake surface.

## Why

Unit tests for the candidate intake pipeline, whose implementation lives in the bench module after the split. The intake logic is verified through the re-exported surface.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
