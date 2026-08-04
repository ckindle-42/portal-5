---
id: unit-sec-tests-test_evidence_chain_validity
kind: mixed
title: "Security tests \u2014 test_evidence_chain_validity"
sources:
- type: code
  path: portal/modules/security/tests/test_evidence_chain_validity.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.5632262
updated_at: 1785800626.5632262
---

Unit tests for the security module's test_evidence_chain_validity surface.

## Why

A chain that broke an invariant would let a conclusion rest on evidence that never existed. The validity invariants for the red-to-evidence-to-blue chain are what keep each link traceable, and the tests pin every invariant.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
