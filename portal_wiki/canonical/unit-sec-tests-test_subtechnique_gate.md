---
id: unit-sec-tests-test_subtechnique_gate
kind: mixed
title: "Security tests \u2014 test_subtechnique_gate"
sources:
- type: code
  path: portal/modules/security/tests/test_subtechnique_gate.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.563243
updated_at: 1785800626.563243
---

Unit tests for the security module's test_subtechnique_gate surface.

## Why

The sibling-discriminator gate prevents one technique's signature from matching its sibling, and the regression tests pin it. A signature that matched a sibling would produce false detections, so the discriminator is the gate's load-bearing piece.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
