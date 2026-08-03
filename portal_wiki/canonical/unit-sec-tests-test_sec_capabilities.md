---
id: unit-sec-tests-test_sec_capabilities
kind: mixed
title: "Security tests \u2014 test_sec_capabilities"
sources:
- type: code
  path: portal/modules/security/tests/test_sec_capabilities.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.563241
updated_at: 1785800626.563241
---

Unit tests for the security module's test_sec_capabilities surface.

## Why

The capability surface is exercised hermetically so a capability regression is caught without a live bench. The capability modules are verified synthetically, which is what lets CI catch a capability break without the lab.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
