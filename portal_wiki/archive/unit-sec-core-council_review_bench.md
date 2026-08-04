---
id: unit-sec-core-council_review_bench
kind: mixed
title: "Council review bench \u2014 council mechanism measurement"
sources:
- type: code
  path: portal/modules/security/core/council_review_bench.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800295.902837
updated_at: 1785800295.902837
---

The bench that measures the council mechanism itself — whether the N-interpreter vote improves verdict quality over a single interpreter.

## Why

A mechanism that costs N model calls must earn its cost: the review bench compares the council's verdict against a single interpreter's on the same cases, and the measurement is what justifies (or fails to justify) the added expense.

## Interfaces

The bench that measures the council mechanism itself — whether the N-interpreter vote improves verdict quality over a single interpreter lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
