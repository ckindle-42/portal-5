---
id: unit-sec-tests-test_technique_signatures
kind: mixed
title: "Security tests \u2014 test_technique_signatures"
sources:
- type: code
  path: portal/modules/security/tests/test_technique_signatures.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.5632498
updated_at: 1785800626.5632498
---

Unit tests for the security module's test_technique_signatures surface.

## Why

The signatures must distinguish a technique from its siblings, and the tests pin the distinguishing content. A signature that could not distinguish its technique would make the technique reference ambiguous.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
