---
id: unit-sec-tests-test_playbooks
historical: true
kind: mixed
title: "Security tests \u2014 test_playbooks"
sources:
- type: code
  path: portal/modules/security/tests/test_playbooks.py
  commit: 862c7b11
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests

---

Unit tests for the security module's test_playbooks surface.

## Why

Unit tests for the security playbooks, the bounded engagement programs. The playbook's scope, budget, and stop/escalate blocks are the autonomy bounds, and the tests pin them.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
