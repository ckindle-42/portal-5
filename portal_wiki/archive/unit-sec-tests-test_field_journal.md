---
id: unit-sec-tests-test_field_journal
kind: mixed
title: "Security tests \u2014 test_field_journal"
sources:
- type: code
  path: portal/modules/security/tests/test_field_journal.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986339
updated_at: 1785800599.986339
---

Unit tests for the security module's test_field_journal surface.

## Why

Unit tests for the security field journal, the observed-fact engagement memory. The journal's only-observed-facts rule is what keeps the loop's memory from being contaminated by inference.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
