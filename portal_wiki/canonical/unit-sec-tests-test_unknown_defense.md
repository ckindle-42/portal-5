---
id: unit-sec-tests-test_unknown_defense
kind: mixed
title: "Security tests \u2014 test_unknown_defense"
sources:
- type: code
  path: portal/modules/security/tests/test_unknown_defense.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.563252
updated_at: 1785800626.563252
---

Unit tests for the security module's test_unknown_defense surface.

## Why

The unknown case must be representable rather than coerced into a wrong known match. The unknown-defense tests pin the similarity tiers and the U1-U6 invariants that keep the unknown case honest.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
