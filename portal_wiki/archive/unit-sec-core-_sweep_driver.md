---
id: unit-sec-core-_sweep_driver
kind: mixed
title: "Sweep driver \u2014 security bench orchestration"
sources:
- type: code
  path: portal/modules/security/core/_sweep_driver.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800295.902818
updated_at: 1785800295.902818
---

The sweep driver orchestrates the security bench runs: the model/prompt grid, the phase sequencing, and the result aggregation across a sweep.

## Why

A security bench sweep is a grid of models and prompts run in phases, and the driver is what sequences the grid so the runs are comparable — the same prompts across the same models under the same conditions. Without it, each run would be a bespoke invocation and the comparison would mean nothing.

## Interfaces

The sweep driver orchestrates the security bench runs: the model/prompt grid, the phase sequencing, and the result aggregation across a sweep lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
