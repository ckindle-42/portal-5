---
id: unit-sec-core-ctf_bench
kind: mixed
title: "CTF bench \u2014 captured-flag ground truth"
sources:
- type: code
  path: portal/modules/security/core/ctf_bench.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394144
updated_at: 1785800269.394144
---

The CTF bench targeting the MBPTL lab (vmid 300) or vulhub containers, where a captured flag is unambiguous ground truth.

## Why

A captured flag is the cleanest possible bench signal — binary ground truth with no scoring ambiguity. The bench drives the lab and scores on whether the flag is captured, which is why the CTF lane is the most objective measurement the security suite has.

## Interfaces

The CTF bench targeting the MBPTL lab (vmid 300) or vulhub containers, where a captured flag is unambiguous ground truth lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
