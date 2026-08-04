---
id: unit-scripts-update_grafana_benchmarks
kind: mixed
title: "Script \u2014 update_grafana_benchmarks"
sources:
- type: code
  path: scripts/update_grafana_benchmarks.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799568.945937
updated_at: 1785799568.945937
---

Writes bench TPS results to Grafana, with input selection and dry-run modes.

## Why

The TPS numbers are the fleet performance signal, and pushing them to Grafana makes the trend visible; the dry-run and input-selection modes make the update reviewable before it writes.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
