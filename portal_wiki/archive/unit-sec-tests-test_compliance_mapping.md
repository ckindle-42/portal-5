---
id: unit-sec-tests-test_compliance_mapping
kind: mixed
title: "Security tests \u2014 test_compliance_mapping"
sources:
- type: code
  path: portal/modules/security/tests/test_compliance_mapping.py
  commit: bdbf509f
last_generated_commit: bdbf509f
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- tests
created_at: 1785800626.563222
updated_at: 1785800626.563222
---

Unit tests for the security module's test_compliance_mapping surface.

## Why

A finding mapped to the wrong framework would misstate the compliance posture in the report. The compliance-mapping and matrix schema dimension is what attributes findings to their frameworks, and the tests pin the mapping so the report is trustworthy.

## Interfaces

The suite exercises the security module hermetically (in-memory or mocked data, no live lab, no Docker) and reports pass/fail per test.

## Gotchas

As a security-module test it must run with no live lab and no Docker, and it is known to write through real runtime paths — the discipline requires checking git status after running the security test tree.
