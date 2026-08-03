---
id: unit-sec-core-cloud_bench
kind: mixed
title: "Cloud bench \u2014 no cloud lane"
sources:
- type: code
  path: portal/modules/security/core/cloud_bench.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.39414
updated_at: 1785800269.39414
---

The cloud bench placeholder documenting that Portal has no cloud lane, even though cloud is where most real environments live.

## Why

The absence is deliberate and documented rather than accidental: a cloud bench would need cloud credentials and external dependencies, both of which the zero-cloud promise forbids. The placeholder records the boundary so a future task does not silently re-add a cloud dependency.

## Interfaces

The cloud bench placeholder documenting that Portal has no cloud lane, even though cloud is where most real environments live lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
