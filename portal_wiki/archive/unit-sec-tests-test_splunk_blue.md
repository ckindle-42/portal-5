---
id: unit-sec-tests-test_splunk_blue
historical: true
kind: mixed
title: "Security tests \u2014 test_splunk_blue"
sources:
- type: code
  path: portal/modules/security/tests/test_splunk_blue.py
  commit: 862c7b11
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests

---

Unit tests for the security module's test_splunk_blue surface.

## Why

Tests for the Splunk SIEM integration and blue-triage, synthetic with no live Splunk. The SIEM integration is verified hermetically so a CI run never needs a real Splunk.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
