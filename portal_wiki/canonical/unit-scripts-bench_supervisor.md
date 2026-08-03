---
id: unit-scripts-bench_supervisor
kind: mixed
title: "Script \u2014 bench_supervisor"
sources:
- type: code
  path: scripts/bench_supervisor.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799454.6134698
updated_at: 1785799454.6134698
---

Launches the security bench as a subprocess, tails the log, detects known failure patterns across target/lab, model, and bench-logic classes, and takes predefined corrective actions by calling existing primitives — no LLM, no offensive capability, no frontier agent.

## Why

A multi-hour bench run needs a supervisor that can recognise the known failure modes and recover without a human at the keyboard — but the corrective actions must be bounded and reversible, which is why it calls existing primitives rather than improvising. The no-LLM, no-offensive-capability constraint is the safety boundary: the supervisor observes and acts on a fixed menu, it does not reason about the attack.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
