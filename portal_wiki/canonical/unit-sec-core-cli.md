---
id: unit-sec-core-cli
kind: mixed
title: "Security CLI \u2014 bench and engagement dispatcher"
sources:
- type: code
  path: portal/modules/security/core/cli.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800295.9028301
updated_at: 1785800295.9028301
---

The security module's argparse CLI: the bench runner, self-index, stage2-propose, candidate-eval, compliance-report, and the engagement commands. The largest file in the core.

## Why

The CLI is the operator surface for the whole security module — every bench, every engagement command, every report goes through its argument parser. Its size reflects the breadth of the surface, and the argv pass-through from the module CLI keeps the two entry points behaving identically.

## Interfaces

The security module's argparse CLI: the bench runner, self-index, stage2-propose, candidate-eval, compliance-report, and the engagement commands lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
