---
id: unit-scripts-v2_corpus_baseline
kind: mixed
title: "Script \u2014 v2_corpus_baseline"
sources:
- type: code
  path: scripts/v2_corpus_baseline.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799580.002317
updated_at: 1785799580.002317
---

Produces the V2 corpus baseline from a detached pre-V3 checkout, supplying only V2 section fields with no mentor, budgets, barrier tools, or V4 switches.

## Why

A baseline that accidentally includes V3 or V4 behaviour would not be a baseline — it would already contain the change being measured. The deliberate V2-only field supply is what makes the detached checkout produce a pure before-state.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
