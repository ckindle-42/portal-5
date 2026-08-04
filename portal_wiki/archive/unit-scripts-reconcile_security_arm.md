---
id: unit-scripts-reconcile_security_arm
kind: mixed
title: "Script \u2014 reconcile_security_arm"
sources:
- type: code
  path: scripts/reconcile_security_arm.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799550.662385
updated_at: 1785799550.662385
---

Closes the loop the RBP upgrade left open: discovers the live world, grounds every entry in fact, and applies updates so the declared world matches reality — deterministically.

## Why

The code declares a world of targets and tools; the live lab may differ, and a declared world that diverges from reality makes every later phase operate on a fiction. The reconciliation grounds the declaration in discovered fact and applies the deterministic updates that close the gap.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
