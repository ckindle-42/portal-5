---
id: unit-sec-core-__init__
kind: mixed
title: "Security core \u2014 RBP engine package facade"
sources:
- type: code
  path: portal/modules/security/core/__init__.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394124
updated_at: 1785800269.394124
---

The security core is the RBP engine, relocated intact from its historical home: the chain runner, blue/red orchestration, evidence, scoring, the CLI, and every bench. The package `__init__` is the facade that re-exports the public surface so the module can be imported as a whole.

## Why

The facade exists because the RBP engine is a large, internally-wired codebase and the modularization rule was "relocate intact" — the surface must stay importable as one package while the internals keep their original wiring. Re-exporting the key symbols (config, prompts, scoring, the exec sequences, main) is what keeps every external importer working across the relocation.

## Interfaces

The security core is the RBP engine, relocated intact from its historical home: the chain runner, blue/red orchestration, evidence, scoring, the CLI, and every bench lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
