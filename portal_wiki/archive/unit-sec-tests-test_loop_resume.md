---
id: unit-sec-tests-test_loop_resume
historical: true
kind: mixed
title: "Security tests \u2014 test_loop_resume"
sources:
- type: code
  path: portal/modules/security/tests/test_loop_resume.py
  commit: 862c7b11
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests

---

Unit tests for the security module's test_loop_resume surface.

## Why

Tests for checkpoint round-trip and resume semantics, the come-look-mechanism. A resume that lost the checkpoint would restart the engagement from scratch, so the round-trip is pinned.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
