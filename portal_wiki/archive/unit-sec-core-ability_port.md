---
id: unit-sec-core-ability_port
historical: true
kind: mixed
title: "Ability port \u2014 capability probe surface"
sources:
- type: code
  path: portal/modules/security/core/ability_port.py
  commit: 699b6207
claims: []
confidence: high
tags:
- authored-v1
- module
- security

---

The ability-port probe that exercises a workspace's declared capability through the pipeline, checking whether the served behaviour matches the claimed ability.

## Why

A workspace that declares a capability but cannot deliver it is a silent lie in the catalog. The ability port is the probe that drives the declared capability and checks the behaviour, which is what turns a claim into a verified fact or a finding.

## Interfaces

The ability-port probe that exercises a workspace's declared capability through the pipeline, checking whether the served behaviour matches the claimed ability lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
