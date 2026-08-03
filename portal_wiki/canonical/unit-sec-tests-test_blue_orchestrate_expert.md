---
id: unit-sec-tests-test_blue_orchestrate_expert
kind: mixed
title: "Security tests \u2014 test_blue_orchestrate_expert"
sources:
- type: code
  path: portal/modules/security/tests/test_blue_orchestrate_expert.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.986288
updated_at: 1785800599.986288
---

Unit tests for the security module's test_blue_orchestrate_expert surface.

## Why

Tests for the expert section of the blue orchestrator (fed, no tools). The expert section is where the model concludes from the fed material, and its tests pin the no-tools contract.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
