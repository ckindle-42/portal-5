---
id: unit-tests-lib-results
kind: mixed
title: "Tests lib results \u2014 shared result model + classification"
sources:
- type: code
  path: tests/lib/results.py
  commit: f2f2516d
last_generated_commit: f2f2516d
claims: []
confidence: high
tags:
- authored-v1
- tests
- lib
created_at: 1785798250.599473
updated_at: 1785798250.599473
---

`results.py` is the result model and recording helper for the acceptance
tests: it defines the per-scenario result shape, records outcomes, emits
reports, and classifies passes and failures.

## Why

Every harness produces results, and a result shape that varies per harness
makes cross-harness comparison meaningless. The module defines the one result
model — scenario, verdict, assertion outcomes, timing — that the acceptance
drivers and the matrix both record into, so a report from one harness is
comparable to a report from another. The classification logic (what counts
as pass vs fail vs skipped) lives here once rather than being re-derived by
each harness's reporting code.

## Interfaces

The dataclass result model, the recording helpers, and the emission and
classification functions that turn a run's records into a report.

## Gotchas

The classification thresholds are the contract the reports build on — a
harness that reclassifies a verdict differently would produce a report that
contradicts another harness's on the same scenario.
