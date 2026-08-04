---
id: unit-sec-core-stage2_propose
kind: mixed
title: "Stage2 propose \u2014 coverage-gap proposal stage"
sources:
- type: code
  path: portal/modules/security/core/stage2_propose.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800295.902848
updated_at: 1785800295.902848
---

The stage-2 proposal stage that converts coverage gaps into concrete proposed detections or scenarios for the growth loop.

## Why

A gap in coverage is an abstraction until it becomes a concrete proposal, and stage2 is the conversion: gap in, proposed detection or scenario out. It is the bridge between the capability graph's gap report and the growth loop's propose step.

## Interfaces

The stage-2 proposal stage that converts coverage gaps into concrete proposed detections or scenarios for the growth loop lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
