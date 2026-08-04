---
id: unit-sec-core-ability_port
kind: mixed
title: "Ability port \u2014 capability probe surface"
sources:
- type: code
  path: portal/modules/security/core/ability_port.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800295.9028249
updated_at: 1785800295.9028249
---

The ability-port probe that exercises a workspace's declared capability through the pipeline, checking whether the served behaviour matches the claimed ability.

## Why

A workspace that declares a capability but cannot deliver it is a silent lie in the catalog. The ability port is the probe that drives the declared capability and checks the behaviour, which is what turns a claim into a verified fact or a finding.

## Interfaces

The ability-port probe that exercises a workspace's declared capability through the pipeline, checking whether the served behaviour matches the claimed ability lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
