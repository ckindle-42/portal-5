---
id: unit-tests-acceptance-comfyui-shim
kind: mixed
title: "Tests comfyui acceptance \u2014 entry shim"
sources:
- type: code
  path: tests/portal5_acceptance_comfyui.py
  commit: 4900007a
last_generated_commit: 4900007a
claims: []
confidence: high
tags:
- authored-v1
- tests
created_at: 1785798804.5717518
updated_at: 1785798804.5717518
---

`portal5_acceptance_comfyui.py` is the stable entry point for the ComfyUI
acceptance driver; all implementation lives in `tests/comfyui/`, and this
file delegates so existing invocations keep working.

## Why

The ComfyUI acceptance was split into a package, and the operator-facing
command (`python3 tests/portal5_acceptance_comfyui.py --section C4`) must
keep working across the restructure. The shim preserves that invocation and
points at the package implementation.

## Interfaces

Delegates to the ComfyUI acceptance package's CLI.

## Gotchas

New features live in the package, not this shim.
