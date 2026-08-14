---
id: unit-sec-core-cred_bench
kind: mixed
title: "Cred bench \u2014 folded into pentest/redteam scenarios"
sources:
- type: code
  path: portal/modules/security/core/cred_bench.py
  commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394142
updated_at: 1785800269.394142
---

The credential-stuffing bench, folded into the pentest and redteam workspaces as scenarios (spray, stuff, MFA-bypass).

## Why

A standalone credential bench would duplicate what the pentest and redteam scenarios already exercise. Folding spray, stuff, and MFA-bypass into those workspaces is what keeps the credential coverage without a parallel bench to maintain.

## Interfaces

The credential-stuffing bench, folded into the pentest and redteam workspaces as scenarios (spray, stuff, MFA-bypass) lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
