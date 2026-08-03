---
id: unit-sec-core-multichain
kind: mixed
title: "Multichain \u2014 parallel interpreter consensus"
sources:
- type: code
  path: portal/modules/security/core/multichain.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.3941681
updated_at: 1785800269.3941681
---

The piece the Council of Agreement is not: the council votes N interpreters over ONE shared evidence pool, whereas multichain runs N independent investigation chains.

## Why

The two mechanisms answer different questions: a council shares one lead investigation and votes on conclusions from the same evidence, while multichain runs independent chains that can disagree because they saw different evidence. Distinguishing them is what keeps each from being used where the other belongs.

## Interfaces

The piece the Council of Agreement is not: the council votes N interpreters over ONE shared evidence pool, whereas multichain runs N independent investigation chains lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
