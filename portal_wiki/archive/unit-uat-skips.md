---
id: unit-uat-skips
historical: true
kind: mixed
title: "UAT skips \u2014 skip rules"
sources:
- type: code
  path: tests/uat/skips.py
  commit: d7dcc96a
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat

---

The UAT skip rules: which sections are skipped under which conditions.

## Why

Some UAT sections are skipped based on the environment or the run mode, and the skip rules centralise that decision so the runner does not embed skip conditions inline. This is what keeps the skip policy inspectable and consistent across runs.

## Interfaces

The skip-condition functions.

## Gotchas

A skip rule that is too eager silently hides failures — the skip conditions are as important to review as the pass/fail assertions.
