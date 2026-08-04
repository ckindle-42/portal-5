---
id: unit-tests-uat-driver-shim
kind: mixed
title: "Tests UAT driver \u2014 operator entry shim"
sources:
- type: code
  path: tests/portal5_uat_driver.py
  commit: 4900007a
last_generated_commit: 4900007a
claims: []
confidence: high
tags:
- authored-v1
- tests
created_at: 1785798815.105887
updated_at: 1785798815.105887
---

`portal5_uat_driver.py` is the stable operator-facing entry for the UAT
driver; the implementation lives in the `tests/uat/` package, and this file
re-exports it so the documented invocation keeps working.

## Why

The UAT driver was modularised into a package, and every UAT run references
`python3 tests/portal5_uat_driver.py`. The shim preserves that entry point
and its run modes (`--all`, section filters, etc.) while the implementation
lives in the package.

## Interfaces

Delegates to the `tests/uat` package driver.

## Gotchas

New UAT features live in the package.
