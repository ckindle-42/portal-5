---
id: unit-sec-core-__main__
kind: mixed
title: "Security core \u2014 module entry point"
sources:
- type: code
  path: portal/modules/security/core/__main__.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.3941288
updated_at: 1785800269.3941288
---

The `python -m portal.modules.security.core` entry that the CLI pass-through targets, loading the environment before importing the modules that read it.

## Why

The entry exists because the security CLI forwards here (`runpy.run_module` on this package), and several modules read the lab environment variables at import time. Loading the env first is what makes the forwarded invocation behave identically to running the core directly.

## Interfaces

The `python -m portal lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
