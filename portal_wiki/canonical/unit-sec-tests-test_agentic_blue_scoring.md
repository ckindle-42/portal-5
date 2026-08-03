---
id: unit-sec-tests-test_agentic_blue_scoring
kind: mixed
title: "Security tests \u2014 test_agentic_blue_scoring"
sources:
- type: code
  path: portal/modules/security/tests/test_agentic_blue_scoring.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.9862678
updated_at: 1785800599.9862678
---

Unit tests for the security module's test_agentic_blue_scoring surface.

## Why

Unit tests for the agentic-blue eval three-tier scoring (exact, parent, tactic). The three-tier scoring is how a near-miss is distinguished from a miss, and the tests pin the tier boundaries.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
