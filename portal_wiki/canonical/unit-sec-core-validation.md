---
id: unit-sec-core-validation
kind: mixed
title: "Validation \u2014 twin-control use-case gate"
sources:
- type: code
  path: portal/modules/security/core/validation.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394176
updated_at: 1785800269.394176
---

A use-case passes only if the finding lands on the vulnerable target AND vanishes on the hardened twin (zero false positives); red, blue, and purple scored independently.

## Why

The twin-control gate is the anti-noise design: a detection that fires on the vulnerable target but also on the hardened twin has false positives, and the twin is what reveals them. Requiring the finding to vanish on the twin is what makes a detection specific, not just sensitive.

## Interfaces

A use-case passes only if the finding lands on the vulnerable target AND vanishes on the hardened twin (zero false positives); red, blue, and purple scored independently lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
