---
id: unit-sec-core-telemetry
kind: mixed
title: "Telemetry \u2014 canonical backend contract"
sources:
- type: code
  path: portal/modules/security/core/telemetry.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800295.902849
updated_at: 1785800295.902849
---

The canonical TelemetryBackend protocol, the TelemetryContract describing each source, and the TelemetryHealth pre-checks that replaced the dual-backend seam.

## Why

The dual-backend seam (two different backend protocols for the blue and matrix paths) was the source of drift — the same telemetry source described differently in each. One canonical protocol and contract is what makes every consumer agree on what a source provides, and the health pre-checks are what catch a broken source before a run depends on it.

## Interfaces

The canonical TelemetryBackend protocol, the TelemetryContract describing each source, and the TelemetryHealth pre-checks that replaced the dual-backend seam lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
