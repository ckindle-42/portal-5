---
id: unit-sec-tests-test_agentic_blue_multitrial
kind: mixed
title: "Security tests \u2014 test_agentic_blue_multitrial"
sources:
- type: code
  path: portal/modules/security/tests/test_agentic_blue_multitrial.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800599.9862652
updated_at: 1785800599.9862652
---

Unit tests for the security module's test_agentic_blue_multitrial surface.

## Why

Unit tests for the agentic-blue eval multi-trial aggregation, all in-memory. Multi-trial aggregation is the statistical core of the eval, and its tests verify the aggregation logic without any backend.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
