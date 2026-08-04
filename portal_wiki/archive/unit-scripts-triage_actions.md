---
id: unit-scripts-triage_actions
kind: mixed
title: "Script \u2014 triage_actions"
sources:
- type: code
  path: scripts/triage_actions.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799561.630837
updated_at: 1785799561.630837
---

Defines the safe, reversible corrective actions the supervisor may take; any triage result outside ALLOWED_ACTIONS is rejected, logged, and paused for a human.

## Why

A supervisor with unbounded actions is dangerous; the fixed, reversible action set is the safety boundary. The reject-and-pause path for an out-of-menu action is the guard that a triage model cannot escalate beyond what the operator authorised.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
