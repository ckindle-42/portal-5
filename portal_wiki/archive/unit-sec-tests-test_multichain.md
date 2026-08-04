---
id: unit-sec-tests-test_multichain
kind: mixed
title: "Security tests \u2014 test_multichain"
sources:
- type: code
  path: portal/modules/security/tests/test_multichain.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.98637
updated_at: 1785800599.98637
---

Unit tests for the security module's test_multichain surface.

## Why

Tests for multichain consolidation, the triage decision across independent investigation chains. The cooling/triage decision is what resolves conflicting chains, and the tests pin it.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
