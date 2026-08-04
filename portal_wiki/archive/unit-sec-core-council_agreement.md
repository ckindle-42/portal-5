---
id: unit-sec-core-council_agreement
kind: mixed
title: "Council agreement \u2014 N-interpreter vote over shared evidence"
sources:
- type: code
  path: portal/modules/security/core/council_agreement.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800295.902835
updated_at: 1785800295.902835
---

The council-of-agreement mechanism: N interpreters vote over ONE shared evidence pool, where one lead investigation hunts and everyone else concludes from the same context.

## Why

The council exists to make blue-orchestration verdicts robust to single-model error, and its design is specifically one-shared-evidence-pool: a lead investigation gathers, the interpreters conclude from identical context, so a disagreement is about the conclusion, not about seeing different evidence. That is what distinguishes it from the multichain's independent chains.

## Interfaces

The council-of-agreement mechanism: N interpreters vote over ONE shared evidence pool, where one lead investigation hunts and everyone else concludes from the same context lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
