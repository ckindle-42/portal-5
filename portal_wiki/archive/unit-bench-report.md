---
id: unit-bench-report
kind: mixed
title: "Bench report \u2014 availability summary + per-tier tables"
sources:
- type: code
  path: tests/benchmarks/bench/report.py
  commit: 4283b625
last_generated_commit: 4283b625
claims: []
confidence: high
tags:
- authored-v1
- tests
- bench
created_at: 1785798450.132231
updated_at: 1785798450.132231
---

`report.py` is the console reporting for the bench: the availability
summary (configured vs available vs tested vs failed) and the per-tier result
tables.

## Why

A bench run produces a result list, but the operator's question is "what did
I configure, what was actually available, and what passed?" — an availability
summary that separates configured-but-unavailable models from tested ones is
what makes a run interpretable. The per-tier tables then present the TPS
results where the operator can compare them. Reporting is kept separate from
measurement so a format change never touches the timing code.

## Interfaces

`_print_availability_report` and the per-tier table printers.

## Gotchas

The configured-vs-available distinction is the key honesty property — a run
that silently omits unavailable models would make the fleet look better
measured than it is.
