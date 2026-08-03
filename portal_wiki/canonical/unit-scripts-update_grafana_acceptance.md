---
id: unit-scripts-update_grafana_acceptance
kind: mixed
title: "Script \u2014 update_grafana_acceptance"
sources:
- type: code
  path: scripts/update_grafana_acceptance.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799565.293922
updated_at: 1785799565.293922
---

Writes the acceptance results to Grafana and archives a JSONL snapshot for trend tracking.

## Why

The acceptance trends need to be visible on the dashboard and retained as a snapshot for later analysis, and the script is the bridge from the results file to both the dashboard and the trend corpus.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
