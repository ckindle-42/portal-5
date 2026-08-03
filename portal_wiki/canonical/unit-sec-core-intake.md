---
id: unit-sec-core-intake
kind: mixed
title: "Intake \u2014 chain split module"
sources:
- type: code
  path: portal/modules/security/core/intake.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.3941572
updated_at: 1785800269.3941572
---

The intake logic split from chain.py, with the public surface unchanged and chain re-exporting it.

## Why

Same split discipline as refusal: the intake logic moved out of the chain monolith so it is independently testable, with chain re-exporting the surface so callers are unaffected.

## Interfaces

The intake logic split from chain lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
