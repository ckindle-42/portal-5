---
id: unit-sec-tests-test_investigation_agents
kind: mixed
title: "Security tests \u2014 test_investigation_agents"
sources:
- type: code
  path: portal/modules/security/tests/test_investigation_agents.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986349
updated_at: 1785800599.986349
---

Unit tests for the security module's test_investigation_agents surface.

## Why

Tests that five investigation agent roles exist and are distinct. Distinct roles are the investigation design's division of labour, and the tests pin the separation.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
