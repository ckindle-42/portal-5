---
id: unit-sec-core-rescore_run
historical: true
kind: mixed
title: "Rescore \u2014 false-positive-corrected scoring"
sources:
- type: code
  path: portal/modules/security/core/rescore_run.py
  commit: 699b6207
claims: []
confidence: high
tags:
- authored-v1
- module
- security

---

Loads a bench results JSON, removes confirmed false positives from result hits, recomputes step coverage per prompt, prints a comparison, and saves a corrected JSON.

## Why

A bench result that includes false positives overstates the detection's coverage. The rescore removes the confirmed false positives and recomputes, so the corrected JSON is what the operator judges — the difference between a number and the true number.

## Interfaces

Loads a bench results JSON, removes confirmed false positives from result hits, recomputes step coverage per prompt, prints a comparison, and saves a corrected JSON lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
