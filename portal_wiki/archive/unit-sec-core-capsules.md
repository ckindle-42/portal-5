---
id: unit-sec-core-capsules
kind: mixed
title: "Capsules \u2014 replayable proof receipts"
sources:
- type: code
  path: portal/modules/security/core/capsules.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394154
updated_at: 1785800269.394154
---

A proof capsule is a self-contained, integrity-hashed JSON an operator can replay to re-confirm a finding without the original engagement, following the ptai schema.

## Why

A finding is only as durable as its evidence, and the capsule makes the evidence self-contained and verifiable — the integrity hash proves it was not altered since capture. The replay property is what lets a finding be re-confirmed after the engagement is gone.

## Interfaces

A proof capsule is a self-contained, integrity-hashed JSON an operator can replay to re-confirm a finding without the original engagement, following the ptai schema lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
