---
id: unit-sec-core-trace
historical: true
kind: mixed
title: "Trace \u2014 canonical trace-row schema"
sources:
- type: code
  path: portal/modules/security/core/trace.py
  commit: 699b6207
claims: []
confidence: high
tags:
- authored-v1
- module
- security

---

The canonical trace-row schema that all four trace-emitting paths conform to, additive on top of existing shapes.

## Why

Four paths emitting different trace shapes would make tracing unusable — consumers would have to handle each shape. The canonical schema is the contract all four conform to, and the additive design means existing consumers migrate at their own pace rather than breaking on the change.

## Interfaces

The canonical trace-row schema that all four trace-emitting paths conform to, additive on top of existing shapes lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
