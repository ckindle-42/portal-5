---
id: unit-scripts-collapse_snapshot
kind: mixed
title: "Script \u2014 collapse_snapshot"
sources:
- type: code
  path: scripts/collapse_snapshot.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799469.084564
updated_at: 1785799469.084564
---

Captures the counts every phase of the collapse program changes, so each phase's before/after diff is measured. Read-only — never writes to the config or wiki trees.

## Why

A restructuring program needs a before/after measurement per phase, and a snapshot that writes to the trees it measures would corrupt the measurement. The read-only contract is what keeps each phase's diff attributable to that phase rather than to the snapshot tool itself.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
