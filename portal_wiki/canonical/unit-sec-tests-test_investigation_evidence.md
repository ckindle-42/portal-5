---
id: unit-sec-tests-test_investigation_evidence
kind: mixed
title: "Security tests \u2014 test_investigation_evidence"
sources:
- type: code
  path: portal/modules/security/tests/test_investigation_evidence.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986351
updated_at: 1785800599.986351
---

Unit tests for the security module's test_investigation_evidence surface.

## Why

Tests for the investigation evidence record and case notebook. The evidence schema and the notebook's per-case scoping are the trust contract of the investigation layer.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
