---
id: unit-uat-cli
kind: mixed
title: "UAT CLI \u2014 section-selection entry"
sources:
- type: code
  path: tests/uat/cli.py
  commit: 85bb65bd
last_generated_commit: 85bb65bd
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785799336.099338
updated_at: 1785799336.099338
---

The UAT CLI logic extracted from the driver monolith (phase D). The operator entry point remains `tests/portal5_uat_driver.py`.

## Why

The CLI turns the operator invocation into a run — section selection, run modes, and the flags — while the top-level driver stays the documented entry. Keeping the CLI logic here means the entry shim stays thin and the argument handling is testable on its own.

## Interfaces

The CLI argument parsing and section-selection logic.

## Gotchas

The operator-facing command must keep working through the top-level driver — the CLI module is the implementation behind it.
