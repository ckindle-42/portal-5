---
id: unit-sec-tests-test_compliance_report
kind: mixed
title: "Security tests \u2014 test_compliance_report"
sources:
- type: code
  path: portal/modules/security/tests/test_compliance_report.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.5632231
updated_at: 1785800626.5632231
---

Unit tests for the security module's test_compliance_report surface.

## Why

The report is the operator's compliance view, and its tests pin the generation across the frameworks. A report that mis-generated a framework section would mislead the compliance decision, so the generator is verified.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
