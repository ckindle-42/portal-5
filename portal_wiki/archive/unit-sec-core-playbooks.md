---
id: unit-sec-core-playbooks
kind: mixed
title: "Playbooks \u2014 bounded engagement programs"
sources:
- type: code
  path: portal/modules/security/core/playbooks.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394159
updated_at: 1785800269.394159
---

A playbook is a YAML file describing an engagement: phases with depends_on, conditions, and steps, plus mandatory scope, budget, and stop/escalate blocks so the autonomy loop has a bounded program.

## Why

Autonomy without bounds is danger: a loop that can act indefinitely would burn budget and escalate past its authority. The mandatory scope, budget, and stop/escalate blocks are what keep the autonomy loop bounded — every engagement is a program with explicit limits.

## Interfaces

A playbook is a YAML file describing an engagement: phases with depends_on, conditions, and steps, plus mandatory scope, budget, and stop/escalate blocks so the autonomy loop has a bounded program lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
