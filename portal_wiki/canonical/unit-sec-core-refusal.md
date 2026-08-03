---
id: unit-sec-core-refusal
kind: mixed
title: "Refusal \u2014 chain split module"
sources:
- type: code
  path: portal/modules/security/core/refusal.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394156
updated_at: 1785800269.394156
---

The refusal-detection logic split from chain.py, with the public surface unchanged and chain re-exporting it.

## Why

The split is mechanical, not behavioural: the refusal logic was extracted so it could be tested and reasoned about independently, and chain re-exports it so the split is invisible to callers.

## Interfaces

The refusal-detection logic split from chain lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
