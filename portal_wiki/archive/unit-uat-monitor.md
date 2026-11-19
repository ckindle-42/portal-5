---
id: unit-uat-monitor
historical: true
kind: mixed
title: "UAT monitor \u2014 run progress monitor"
sources:
- type: code
  path: tests/uat/monitor.py
  commit: d7dcc96a
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat

---

The UAT run progress monitor that reports on a running UAT run.

## Why

A long UAT run needs a progress view so an operator can tell it is advancing rather than hung, and the monitor provides that without disturbing the run.

## Interfaces

The progress-reporting functions.

## Gotchas

The monitor is observational — it must not mutate the run state it reports on.
