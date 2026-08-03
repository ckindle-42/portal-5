---
id: unit-sec-core-loop_cli
kind: mixed
title: "Loop CLI \u2014 engagement loop operator surface"
sources:
- type: code
  path: portal/modules/security/core/loop_cli.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394148
updated_at: 1785800269.394148
---

The engagement-loop operator CLI, whose resume command is exactly what the escalation and stuck notifications carry.

## Why

The loop CLI exists so an operator can act straight from an alert: every engagement-escalated or engagement-stuck notification carries `loop resume <engagement_id>`, and the CLI is the surface that command invokes. The notification-to-command wiring is what makes the loop operable from the alert.

## Interfaces

The engagement-loop operator CLI, whose resume command is exactly what the escalation and stuck notifications carry lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
