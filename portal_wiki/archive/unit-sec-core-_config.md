---
id: unit-sec-core-_config
kind: mixed
title: "Security core config \u2014 BenchConfig dataclass"
sources:
- type: code
  path: portal/modules/security/core/_config.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394132
updated_at: 1785800269.394132
---

The `BenchConfig` dataclass holding the fields that were previously mutated at module level by main and read by the chain, blue, and lab runners.

## Why

The module-level-mutation pattern was the config's original shape, and it was fragile — a runner that read a global after main changed it could see half-updated state. Moving every value onto the dataclass and passing `cfg` to the functions that need it is what makes the config explicit and the runners deterministic.

## Interfaces

The `BenchConfig` dataclass holding the fields that were previously mutated at module level by main and read by the chain, blue, and lab runners lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
