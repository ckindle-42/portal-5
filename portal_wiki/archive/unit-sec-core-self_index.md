---
id: unit-sec-core-self_index
kind: mixed
title: "Self-index \u2014 engagement evidence index"
sources:
- type: code
  path: portal/modules/security/core/self_index.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800295.902845
updated_at: 1785800295.902845
---

The self-index that inventories the engagement artifacts: results, checkpoints, and evidence, so the module can answer what it has produced.

## Why

A long-running engagement program produces a large body of artifacts, and an index over them is what lets the module and the operator answer "what exists and where". The self-index is the module's own inventory.

## Interfaces

The self-index that inventories the engagement artifacts: results, checkpoints, and evidence, so the module can answer what it has produced lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
