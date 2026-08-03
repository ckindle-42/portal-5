---
id: unit-sec-tests-__init__
kind: mixed
title: "Security tests \u2014 __init__"
sources:
- type: code
  path: portal/modules/security/tests/__init__.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986249
updated_at: 1785800599.986249
---

Unit tests for the security module's __init__ surface.

## Why

The security module test tree root, marking the suite that exercises the RBP engine and its benches. The namespace exists so the security tests have a stable import home, and the module tests are known to write through real runtime paths — which is why the CLAUDE.md discipline requires checking git status after running them.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
