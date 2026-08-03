---
id: unit-compliance-module-config-only
kind: mixed
title: "Compliance module \u2014 config-only discipline namespace"
sources:
- type: code
  path: portal/modules/compliance/__init__.py
  commit: 1a0e2df4
last_generated_commit: 1a0e2df4
claims: []
confidence: high
tags:
- authored-v1
- module
- compliance
created_at: 1785794863.449652
updated_at: 1785794863.449652
---

The compliance module is a config-only discipline, the same shape as the
general module in the modularization program: there is no dedicated compliance
MCP server or Portal-authored source tree to relocate. Its entire surface is a
workspace (`auto-compliance`, declared in `config/portal.yaml`) plus the
compliance-report generator that stays inside the security module because it
is the RBP engine's own output formatter, not the discipline's implementation.

## Why

Keeping compliance as a named module rather than folding it into security
preserves the module/workspace wiring that `sync-config` renders — the module
tag on `auto-compliance` is what hides or shows that workspace when the
discipline is toggled. The package exists to be that tag's home and to record
the boundary decision explicitly: RBP's `compliance_report.py` stays put by
design, and a future compliance implementation would live here instead of
duplicating the report generator.

## Interfaces

The `__init__.py` declares no callable surface. Its purpose is the namespace
marker for the module and the docstring that records why the module is
config-only — the actual workspace lives in `portal.yaml` and the report
generator in `portal/modules/security/core/compliance_report.py`.
