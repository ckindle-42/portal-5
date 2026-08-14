---
id: unit-sec-core-decision_engine
kind: mixed
title: "Decision engine \u2014 promoted to platform agent rank"
sources:
- type: code
  path: portal/modules/security/core/decision_engine.py
  commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394145
updated_at: 1785800269.394145
---

The decision engine, promoted to `portal.platform.agent.rank` and re-exported here for backward compatibility.

## Why

The promotion moved the ranking logic to the platform agent layer where the whole platform can use it, and the re-export preserves the historical import path so existing security imports and the bench integration keep working through the relocation.

## Interfaces

The decision engine, promoted to `portal lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
