---
id: unit-sec-core-bench_integration
kind: mixed
title: "Bench integration \u2014 no-op-safe module hooks"
sources:
- type: code
  path: portal/modules/security/core/bench_integration.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.3941388
updated_at: 1785800269.3941388
---

The integration shims that let the bench operate even when a module is absent, each step no-op'ing safely.

## Why

A bench that crashes because an optional module is not present is a bench that cannot run in a minimal deployment. The no-op contract is what makes the integration safe to run at any point — every step degrades to doing nothing rather than raising.

## Interfaces

The integration shims that let the bench operate even when a module is absent, each step no-op'ing safely lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
