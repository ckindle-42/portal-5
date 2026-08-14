---
id: unit-scripts-portal5-powermetrics
kind: mixed
title: "Script \u2014 portal5-powermetrics"
sources:
- type: code
  path: scripts/portal5-powermetrics.py
  commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799547.025759
updated_at: 1785799547.025759
---

Runs powermetrics continuously, parses the output, and exposes current power plus 1-min/10-min averages on a Unix domain socket.

## Why

The energy accounting needs a continuous power signal, and a Unix socket is the lightweight transport that lets the pipeline poll current watts without a heavier service. The averages are what make the instantaneous reading stable enough to charge per-request energy.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
