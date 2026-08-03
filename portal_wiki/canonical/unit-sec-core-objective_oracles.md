---
id: unit-sec-core-objective_oracles
kind: mixed
title: "Objective oracles \u2014 path-independent end-state verifiers"
sources:
- type: code
  path: portal/modules/security/core/objective_oracles.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394151
updated_at: 1785800269.394151
---

Path-independent verifiers of objective end-states for emergent runs, one oracle per terminal-state class, registered experimental until bench-gated.

## Why

An emergent run can reach the same end-state by many paths, so scoring it on the path would be wrong — the oracle verifies the end-state independently of how it was reached. The experimental-until-gated registration is the discipline: an oracle is not trusted for scoring until the bench proves it.

## Interfaces

Path-independent verifiers of objective end-states for emergent runs, one oracle per terminal-state class, registered experimental until bench-gated lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
