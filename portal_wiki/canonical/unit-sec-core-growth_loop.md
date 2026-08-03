---
id: unit-sec-core-growth_loop
kind: mixed
title: "Growth loop \u2014 propose/prove/confirm capability growth"
sources:
- type: code
  path: portal/modules/security/core/growth_loop.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800295.902838
updated_at: 1785800295.902838
---

The growth loop that proposes new detections and scenarios to close capability gaps, proves them, and confirms the proven ones into the library.

## Why

The loop is the self-improving mechanism: a gap in the capability graph generates a proposed detection, the proposal is proven against the corpus, and a proven one is confirmed into the library — the cycle the integration test proves end to end. It is the difference between a static library and one that grows.

## Interfaces

The growth loop that proposes new detections and scenarios to close capability gaps, proves them, and confirms the proven ones into the library lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
