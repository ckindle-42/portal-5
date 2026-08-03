---
id: unit-tests-persona-matrix-shim
kind: mixed
title: "Tests persona-matrix \u2014 relocated-package compat shim"
sources:
- type: code
  path: tests/portal5_persona_matrix.py
  commit: 4900007a
last_generated_commit: 4900007a
claims: []
confidence: high
tags:
- authored-v1
- tests
created_at: 1785798811.610508
updated_at: 1785798811.610508
---

`portal5_persona_matrix.py` is the stable entry for the persona-matrix
harness; the implementation lives in `portal/modules/eval/persona_matrix`,
and this file is a compat shim for the relocated package.

## Why

The persona-matrix harness was relocated into the eval module as part of the
modularization, and the operator-facing invocation (`--workspace
auto-coding`) must keep working. The shim preserves the historical command
while pointing at the canonical package.

## Interfaces

Delegates to the eval package's persona-matrix CLI.

## Gotchas

New features live in the eval package; the shim is the compatibility bridge.
