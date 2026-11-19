---
id: unit-sec-tests-test_sec_capabilities
historical: true
kind: mixed
title: "Security tests \u2014 test_sec_capabilities"
sources:
- type: code
  path: portal/modules/security/tests/test_sec_capabilities.py
  commit: 862c7b11
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests

---

Unit tests for the security module's test_sec_capabilities surface.

## Why

The capability surface is exercised hermetically so a capability regression is caught without a live bench. The capability modules are verified synthetically, which is what lets CI catch a capability break without the lab.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
