---
id: unit-sec-core-continuous_eval
kind: mixed
title: "Continuous eval \u2014 ongoing capability evaluation"
sources:
- type: code
  path: portal/modules/security/core/continuous_eval.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800295.902834
updated_at: 1785800295.902834
---

The continuous-evaluation loop that keeps the security capability surface measured over time, re-running the eval grid on a cadence.

## Why

A capability measured once is a snapshot; the continuous loop is what makes the measurement current. Running the eval on a cadence is what catches a regression after a model or tool change rather than at the next manual bench.

## Interfaces

The continuous-evaluation loop that keeps the security capability surface measured over time, re-running the eval grid on a cadence lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
