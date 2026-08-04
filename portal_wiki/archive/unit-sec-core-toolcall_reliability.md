---
id: unit-sec-core-toolcall_reliability
kind: mixed
title: "Tool-call reliability \u2014 well-formed tool-call axis"
sources:
- type: code
  path: portal/modules/security/core/toolcall_reliability.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394172
updated_at: 1785800269.394172
---

The instrument that measures whether a model can emit a well-formed tool call, filling the blind spot where the chain-test has no axis for it.

## Why

The chain-test measures execution, coherence, and pivot but not tool-call well-formedness — a blind spot that hid a real failure where a model produced garbled text where JSON should be and then spiralled into meta-commentary. The instrument makes that failure measurable instead of hidden.

## Interfaces

The instrument that measures whether a model can emit a well-formed tool call, filling the blind spot where the chain-test has no axis for it lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
