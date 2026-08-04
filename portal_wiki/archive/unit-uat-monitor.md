---
id: unit-uat-monitor
kind: mixed
title: "UAT monitor \u2014 run progress monitor"
sources:
- type: code
  path: tests/uat/monitor.py
  commit: 85bb65bd
last_generated_commit: 85bb65bd
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785799326.3474188
updated_at: 1785799326.3474188
---

The UAT run progress monitor that reports on a running UAT run.

## Why

A long UAT run needs a progress view so an operator can tell it is advancing rather than hung, and the monitor provides that without disturbing the run.

## Interfaces

The progress-reporting functions.

## Gotchas

The monitor is observational — it must not mutate the run state it reports on.
