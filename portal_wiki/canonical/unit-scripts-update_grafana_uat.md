---
id: unit-scripts-update_grafana_uat
kind: mixed
title: "Script \u2014 update_grafana_uat"
sources:
- type: code
  path: scripts/update_grafana_uat.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799572.648927
updated_at: 1785799572.648927
---

Writes UAT results to Grafana with dry-run and input-selection modes.

## Why

UAT pass/fail trends belong on the dashboard, and the script is the bridge from the UAT results file to Grafana with the review modes that make a bad push catchable first.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
