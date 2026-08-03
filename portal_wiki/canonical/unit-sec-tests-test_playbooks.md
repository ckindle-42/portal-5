---
id: unit-sec-tests-test_playbooks
kind: mixed
title: "Security tests \u2014 test_playbooks"
sources:
- type: code
  path: portal/modules/security/tests/test_playbooks.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.98638
updated_at: 1785800599.98638
---

Unit tests for the security module's test_playbooks surface.

## Why

Unit tests for the security playbooks, the bounded engagement programs. The playbook's scope, budget, and stop/escalate blocks are the autonomy bounds, and the tests pin them.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
