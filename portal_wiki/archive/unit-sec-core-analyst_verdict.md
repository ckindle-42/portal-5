---
id: unit-sec-core-analyst_verdict
kind: mixed
title: "Analyst verdict \u2014 blue-orchestration outcome taxonomy"
sources:
- type: code
  path: portal/modules/security/core/analyst_verdict.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394136
updated_at: 1785800269.394136
---

The analyst-verdict taxonomy for the blue orchestration loop, extended in V2 to carry the similar/variant/novel result from the similarity computation so the emerging-threat case is representable.

## Why

A verdict taxonomy that can only say hit/miss cannot represent an emerging threat — a detection that is *close but novel* is the case that matters most. The V2 extension adds the similar/variant/novel axis so that case is representable rather than coerced into a wrong exact match, which is what keeps the blue loop honest about near-misses.

## Interfaces

The analyst-verdict taxonomy for the blue orchestration loop, extended in V2 to carry the similar/variant/novel result from the similarity computation so the emerging-threat case is representable lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
