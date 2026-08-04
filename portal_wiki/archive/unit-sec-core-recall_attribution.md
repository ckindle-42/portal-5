---
id: unit-sec-core-recall_attribution
kind: mixed
title: "Recall attribution \u2014 discriminator-presence question"
sources:
- type: code
  path: portal/modules/security/core/recall_attribution.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800295.902844
updated_at: 1785800295.902844
---

Answers a narrower question than the corpus replay scorer: when a labeled cell did not confirm its expected technique, was that technique's machine-checkable discriminator present in the telemetry returned to the model?

## Why

A miss can mean the model failed to see the evidence or the evidence was never there. Recall attribution separates the two — it checks whether the technique's discriminator was in the returned telemetry, so a miss is attributed to retrieval failure rather than to the model.

## Interfaces

Answers a narrower question than the corpus replay scorer: when a labeled cell did not confirm its expected technique, was that technique's machine-checkable discriminator present in the telemetry returned to the model? lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
