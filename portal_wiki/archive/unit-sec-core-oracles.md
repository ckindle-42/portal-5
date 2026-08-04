---
id: unit-sec-core-oracles
kind: mixed
title: "Oracles \u2014 scenario objective evaluation"
sources:
- type: code
  path: portal/modules/security/core/oracles.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800295.902842
updated_at: 1785800295.902842
---

The oracle functions that judge whether a scenario's objective was met from the model's response, the scoring backbone of the red/blue/purple benches.

## Why

An oracle is the definition of success for a scenario — it decides whether the response achieved the objective, independent of the path. Consistent oracles are what make scenario scores comparable across models and across runs.

## Interfaces

The oracle functions that judge whether a scenario's objective was met from the model's response, the scoring backbone of the red/blue/purple benches lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
